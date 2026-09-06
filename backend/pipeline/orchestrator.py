"""Recovery pipeline / orchestration — the ONLY module that wires the flow (Vikash).

Source of truth: docs/APP_FLOW.md §"Recovery run", docs/TRD.md §"Pipeline".

    observe -> diagnose -> plan -> schema-gate -> twin validate -> safety gate
            -> (only if approved) execute -> updated state

The pipeline owns control flow + error handling. Every domain decision is
delegated to a port (`backend/pipeline/ports.py`). It NEVER lets an AI proposal
reach execution without an `approved` SafetyDecision for the current version.

Unwired ports raise `ModuleNotWired`; the pipeline turns that into an honest
`RunOutcome`, never a fabricated success.

Concurrency: `run()` is synchronous, invoked from the async `/recovery/run`
handler. Fine while every stage is fast in-memory work. When `backend/recovery/`
starts making network calls this moves to a worker thread + threadsafe publish.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.execution.executor import Executor
from backend.models.common import new_run_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import RunOutcome, ViolationLevel
from backend.models.errors import ModuleNotWired
from backend.models.recovery import RecoveryPlan
from backend.models.run import CandidateResult, RecoveryRunResult
from backend.models.safety import PolicyConfig, SafetyDecision, Violation
from backend.models.twin import SimulationResult
from backend.models.validation import SchemaError, parse_plan
from backend.pipeline.ports import (
    Diagnoser,
    DigitalTwin,
    FaultInjector,
    NetworkModel,
    RecoveryPlanner,
    SafetyGate,
    TelemetrySource,
)
from backend.state.manager import StateManager

Publisher = Callable[[str, dict, int | None], None]


class _NotWired:
    """Placeholder port. Any call raises ModuleNotWired naming the owner."""

    def __init__(self, who: str) -> None:
        self._who = who

    def __getattr__(self, name: str):
        def _raise(*_a, **_k):
            raise ModuleNotWired(f"{self._who} is not wired yet")
        return _raise


class Pipeline:
    def __init__(
        self,
        *,
        state: StateManager,
        executor: Executor | None = None,
        network_model: NetworkModel | None = None,
        telemetry: TelemetrySource | None = None,
        faults: FaultInjector | None = None,
        diagnoser: Diagnoser | None = None,
        planner: RecoveryPlanner | None = None,
        twin: DigitalTwin | None = None,
        safety: SafetyGate | None = None,
        policy: PolicyConfig | None = None,
        publisher: Publisher | None = None,
    ) -> None:
        self._state = state
        # The pipeline is the ONLY caller of execution/. api/ never imports it.
        self._executor = executor or Executor(state, network_model=network_model)
        self._telemetry = telemetry or _NotWired("telemetry/ (Sahil)")
        self._faults = faults or _NotWired("faults/ (Sahil)")
        self._diagnoser = diagnoser or _NotWired("diagnosis/ (Yyash)")
        self._planner = planner or _NotWired("recovery/ (Yyash)")
        self._twin = twin or _NotWired("twin/ (Sahil)")
        self._safety = safety or _NotWired("safety/ (Hrishi)")
        self._policy = policy or PolicyConfig()
        self._publish = publisher

    # --- partial flows (used by /recovery/diagnose and /recovery/plan) ---

    def diagnose(self) -> Diagnosis:
        snap = self._state.get_state()
        tel = self._telemetry.derive(snap)
        return self._diagnoser.diagnose(snap, tel, self._active_faults())

    def plan(self) -> tuple[Diagnosis, list[RecoveryPlan]]:
        snap = self._state.get_state()
        tel = self._telemetry.derive(snap)
        dx = self._diagnoser.diagnose(snap, tel, self._active_faults())
        return dx, self._valid_plans(snap, dx)

    # --- the full cycle -------------------------------------------------

    def run(self, auto_apply: bool = True) -> RecoveryRunResult:
        run_id = new_run_id()
        snap = self._state.get_state()
        base = snap.version
        self._emit("recovery", {"run_id": run_id, "stage": "started", "result": None}, base)

        try:
            tel = self._telemetry.derive(snap)
            dx = self._diagnoser.diagnose(snap, tel, self._active_faults())
        except ModuleNotWired as exc:
            return self._finish(run_id, base, RunOutcome.error, str(exc))
        except Exception as exc:  # noqa: BLE001 - diagnosis failure is a normal outcome
            return self._finish(run_id, base, RunOutcome.diagnosis_failed, f"diagnosis failed: {exc}")
        self._emit("diagnosis", {"run_id": run_id, "diagnosis": dx.model_dump(mode="json")}, base)

        try:
            plans = self._valid_plans(snap, dx)
        except ModuleNotWired as exc:
            return self._finish(run_id, base, RunOutcome.error, str(exc), diagnosis=dx)
        except Exception as exc:  # noqa: BLE001
            return self._finish(run_id, base, RunOutcome.no_plan, f"planning failed: {exc}", diagnosis=dx)
        if not plans:
            return self._finish(
                run_id, base, RunOutcome.no_plan, "no schema-valid candidate plan", diagnosis=dx
            )

        candidates: list[CandidateResult] = []
        for plan in plans:
            sim = self._simulate(snap, plan)
            self._emit("simulation", {"run_id": run_id, "result": sim.model_dump(mode="json")}, base)
            decision = self._evaluate(snap, sim, plan)
            self._emit("safety", {"run_id": run_id, "decision": decision.model_dump(mode="json")}, base)
            candidates.append(CandidateResult(plan=plan, simulation=sim, safety=decision))

        approved = [c for c in candidates if c.safety.approved and c.simulation.feasible]
        if not approved:
            return self._finish(
                run_id, base, RunOutcome.no_safe_plan,
                "no candidate passed twin feasibility + safety", diagnosis=dx, candidates=candidates,
            )

        best = max(
            approved,
            key=lambda c: (c.simulation.metrics.availability, -c.simulation.metrics.avg_latency),
        )
        if not auto_apply:
            return self._finish(
                run_id, base, RunOutcome.approved_pending,
                f"plan {best.plan.id} approved; auto_apply disabled",
                diagnosis=dx, candidates=candidates,
            )

        result = self._executor.apply(best.plan, best.safety)
        if not result.ok:
            return self._finish(
                run_id, base, RunOutcome.error, f"execution failed: {result.reason}",
                diagnosis=dx, candidates=candidates,
            )
        return self._finish(
            run_id, base, RunOutcome.applied, f"applied plan {best.plan.id}",
            diagnosis=dx, candidates=candidates,
            applied_plan_id=best.plan.id, resulting_version=result.resulting_version,
        )

    # --- stages ------------------------------------------------------

    def _active_faults(self):
        try:
            return self._faults.active()
        except ModuleNotWired:
            return []  # an empty list is a truthful answer before faults/ exists

    def _valid_plans(self, snap, dx: Diagnosis) -> list[RecoveryPlan]:
        raw_plans = self._planner.plan(snap, dx)
        valid: list[RecoveryPlan] = []
        for p in raw_plans:
            try:
                valid.append(parse_plan(p.model_dump(mode="json"), snap))
            except SchemaError:
                continue  # malformed / out-of-vocabulary candidate is dropped
        return valid

    def _simulate(self, snap, plan: RecoveryPlan) -> SimulationResult:
        try:
            return self._twin.validate(snap.model_copy(deep=True), plan)
        except Exception as exc:  # noqa: BLE001 - stage isolation; one bad candidate never aborts the run
            from backend.models.common import new_sim_id
            return SimulationResult(
                id=new_sim_id(), plan_id=plan.id, based_on_version=snap.version,
                feasible=False, infeasible_reason=f"twin error: {exc}", errors=[str(exc)],
                computed_at=utcnow(),
            )

    def _evaluate(self, snap, sim: SimulationResult, plan: RecoveryPlan) -> SafetyDecision:
        try:
            return self._safety.evaluate(snap, sim, plan, self._policy)
        except Exception as exc:  # noqa: BLE001 - unknown safety result => reject
            return SafetyDecision(
                plan_id=plan.id, based_on_version=snap.version, approved=False,
                violations=[Violation(rule="safety_error", detail=str(exc), level=ViolationLevel.critical)],
                policy_version=self._policy.policy_version, decided_at=utcnow(),
            )

    # --- helpers ---------------------------------------------------

    def _emit(self, event_type: str, payload: dict, version: int | None) -> None:
        if self._publish is not None:
            self._publish(event_type, payload, version)

    def _finish(
        self,
        run_id: str,
        base_version: int,
        outcome: RunOutcome,
        message: str,
        *,
        diagnosis: Diagnosis | None = None,
        candidates: list[CandidateResult] | None = None,
        applied_plan_id: str | None = None,
        resulting_version: int | None = None,
    ) -> RecoveryRunResult:
        result = RecoveryRunResult(
            run_id=run_id, based_on_version=base_version, outcome=outcome, message=message,
            diagnosis=diagnosis, candidates=candidates or [], applied_plan_id=applied_plan_id,
            resulting_version=resulting_version, completed_at=utcnow(),
        )
        if outcome is RunOutcome.error:
            self._emit("error", {"run_id": run_id, "code": "pipeline_error", "message": message}, base_version)
        self._emit(
            "recovery",
            {"run_id": run_id, "stage": "completed", "result": result.model_dump(mode="json")},
            resulting_version if resulting_version is not None else base_version,
        )
        return result
