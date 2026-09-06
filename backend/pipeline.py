"""Recovery pipeline / orchestration — the ONLY module that wires the flow.

Source of truth: docs/ARCHITECTURE.md §5, docs/TRD.md §2.3.

    observe -> diagnose -> plan -> simulate -> safety evaluate -> execute

The pipeline owns control flow and error handling. Every domain decision is
delegated to the owning module through a small Protocol:

    Diagnoser / Planner    -> ai/     (Yyash)   return data only
    Twin                   -> twin/   (Sahil)   returns SimulationResult
    SafetyEvaluator        -> safety/ (Hrishi)  returns SafetyDecision
    TelemetrySource        -> telemetry/ (Sahil)
    FaultSource            -> faults/ (Sahil)
    Executor               -> execution/ (Vikash) applies ONLY approved plans

During Phase 0/1 the teammate ports are `NotImplemented*` stubs. `run()` executes
the real control flow against them and returns an honest RunOutcome
(`diagnosis_failed` / `no_plan` / `no_safe_plan`) — it never fabricates a result.

Concurrency: `run()` is synchronous and, invoked from the async `/recovery/run`
handler, blocks the event loop for its duration. Fine while every stage is fast
in-memory work. Once `ai/` makes network calls this must change — either make the
pipeline async, or dispatch `run()` to a worker thread AND make
`Broadcaster.publish` thread-safe (`loop.call_soon_threadsafe`). Tracked as an
integration risk.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from backend.models.common import new_run_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import RunOutcome, ViolationLevel
from backend.models.errors import PipelineError
from backend.models.faults import Fault
from backend.models.recovery import RecoveryPlan
from backend.models.run import CandidateResult, RecoveryRunResult
from backend.models.safety import PolicyConfig, SafetyDecision, Violation
from backend.models.simulation import SimulationResult
from backend.models.state import NetworkState
from backend.models.telemetry import Telemetry
from backend.execution.executor import Executor
from backend.state.manager import StateManager

Publisher = Callable[[str, dict, int | None], None]


# --- teammate ports ---------------------------------------------------------

class TelemetrySource(Protocol):
    def derive(self, state: NetworkState) -> Telemetry: ...


class FaultSource(Protocol):
    def active(self) -> list[Fault]: ...


class Diagnoser(Protocol):
    def diagnose(self, state: NetworkState, active_faults: list[Fault], telemetry: Telemetry) -> Diagnosis: ...


class Planner(Protocol):
    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]: ...


class Twin(Protocol):
    def simulate(self, state: NetworkState, plan: RecoveryPlan) -> SimulationResult: ...


class SafetyEvaluator(Protocol):
    def evaluate(
        self, before: NetworkState, sim: SimulationResult, plan: RecoveryPlan, policy: PolicyConfig
    ) -> SafetyDecision: ...


# --- Phase 0/1 stubs (replaced by real teammate modules) ------------------

class _Stub:
    _owner = "a teammate module"

    def _fail(self) -> None:
        raise NotImplementedError(f"{self._owner} is not wired yet")


class NotImplementedTelemetry(_Stub, TelemetrySource):
    _owner = "telemetry/ (Sahil)"

    def derive(self, state: NetworkState) -> Telemetry:
        self._fail()


class NotImplementedFaults(_Stub, FaultSource):
    _owner = "faults/ (Sahil)"

    def active(self) -> list[Fault]:
        return []  # empty is a truthful answer before FaultInjector exists


class NotImplementedDiagnoser(_Stub, Diagnoser):
    _owner = "ai/ diagnosis (Yyash)"

    def diagnose(self, state, active_faults, telemetry) -> Diagnosis:
        self._fail()


class NotImplementedPlanner(_Stub, Planner):
    _owner = "ai/ recovery planner (Yyash)"

    def plan(self, state, diagnosis) -> list[RecoveryPlan]:
        self._fail()


class NotImplementedTwin(_Stub, Twin):
    _owner = "twin/ (Sahil)"

    def simulate(self, state, plan) -> SimulationResult:
        self._fail()


class NotImplementedSafety(_Stub, SafetyEvaluator):
    _owner = "safety/ (Hrishi)"

    def evaluate(self, before, sim, plan, policy) -> SafetyDecision:
        self._fail()


# --- the orchestrator ------------------------------------------------------

class Pipeline:
    def __init__(
        self,
        *,
        state: StateManager,
        executor: Executor | None = None,
        telemetry: TelemetrySource | None = None,
        faults: FaultSource | None = None,
        diagnoser: Diagnoser | None = None,
        planner: Planner | None = None,
        twin: Twin | None = None,
        safety: SafetyEvaluator | None = None,
        policy: PolicyConfig | None = None,
        publisher: Publisher | None = None,
    ) -> None:
        self._state = state
        # The pipeline is the ONLY caller of execution/ (invariant 10), so it
        # owns the Executor. `api/` therefore never imports execution/.
        self._executor = executor or Executor(state)
        self._telemetry = telemetry or NotImplementedTelemetry()
        self._faults = faults or NotImplementedFaults()
        self._diagnoser = diagnoser or NotImplementedDiagnoser()
        self._planner = planner or NotImplementedPlanner()
        self._twin = twin or NotImplementedTwin()
        self._safety = safety or NotImplementedSafety()
        self._policy = policy or PolicyConfig()
        self._publish = publisher

    # --- public API ------------------------------------------------------

    def diagnose(self) -> Diagnosis:
        snap = self._state.get_state()
        tel = self._telemetry.derive(snap)
        return self._diagnose(snap, tel)

    def plan(self, diagnosis_id: str | None = None) -> tuple[Diagnosis, list[RecoveryPlan]]:
        snap = self._state.get_state()
        tel = self._telemetry.derive(snap)
        dx = self._diagnose(snap, tel)
        return dx, self._plan(snap, dx)

    def run(self, auto_apply: bool = True) -> RecoveryRunResult:
        run_id = new_run_id()
        snap = self._state.get_state()
        base = snap.version
        self._emit("recovery", {"run_id": run_id, "stage": "started", "result": None}, base)

        try:
            tel = self._telemetry.derive(snap)
        except NotImplementedError as exc:
            return self._finish(run_id, base, RunOutcome.error, f"telemetry not wired: {exc}")

        try:
            dx = self._diagnose(snap, tel)
        except PipelineError as exc:
            return self._finish(run_id, base, RunOutcome.diagnosis_failed, str(exc))
        self._emit("diagnosis", {"run_id": run_id, "diagnosis": dx.model_dump(mode="json")}, base)

        try:
            plans = self._plan(snap, dx)
        except PipelineError as exc:
            return self._finish(run_id, base, RunOutcome.no_plan, str(exc), diagnosis=dx)
        if not plans:
            return self._finish(
                run_id, base, RunOutcome.no_plan, "no schema-valid candidate plans", diagnosis=dx
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
                "no candidate passed safety + feasibility", diagnosis=dx, candidates=candidates,
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

    # --- stages ----------------------------------------------------------

    def _diagnose(self, snap: NetworkState, tel: Telemetry) -> Diagnosis:
        faults = self._faults.active()
        last: Exception | None = None
        for _ in range(2):  # one retry, per ARCHITECTURE §5.1
            try:
                return self._diagnoser.diagnose(snap, faults, tel)
            except Exception as exc:  # noqa: BLE001 - pipeline isolates stage failures
                last = exc
        raise PipelineError(f"diagnosis unavailable: {last}")

    def _plan(self, snap: NetworkState, dx: Diagnosis) -> list[RecoveryPlan]:
        try:
            return list(self._planner.plan(snap, dx))
        except Exception as exc:  # noqa: BLE001
            raise PipelineError(f"planning unavailable: {exc}") from exc

    def _simulate(self, snap: NetworkState, plan: RecoveryPlan) -> SimulationResult:
        try:
            return self._twin.simulate(snap.model_copy(deep=True), plan)
        except Exception as exc:  # noqa: BLE001 - stage isolation
            return SimulationResult(
                plan_id=plan.id,
                based_on_version=snap.version,
                feasible=False,
                infeasible_reason=f"twin error: {exc}",
                errors=[str(exc)],
                computed_at=utcnow(),
            )

    def _evaluate(self, snap: NetworkState, sim: SimulationResult, plan: RecoveryPlan) -> SafetyDecision:
        try:
            return self._safety.evaluate(snap, sim, plan, self._policy)
        except Exception as exc:  # noqa: BLE001 - stage isolation; unknown => reject
            return SafetyDecision(
                plan_id=plan.id,
                based_on_version=snap.version,
                approved=False,
                violations=[Violation(rule="safety_error", detail=str(exc), level=ViolationLevel.critical)],
                policy_version=self._policy.policy_version,
                decided_at=utcnow(),
            )

    # --- helpers -------------------------------------------------------

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
            run_id=run_id,
            based_on_version=base_version,
            outcome=outcome,
            message=message,
            diagnosis=diagnosis,
            candidates=candidates or [],
            applied_plan_id=applied_plan_id,
            resulting_version=resulting_version,
            completed_at=utcnow(),
        )
        # A genuine operational error also surfaces as a dedicated `error` event
        # (BACKEND_SCHEMA.md §7). Expected outcomes (no_plan / no_safe_plan /
        # diagnosis_failed / approved_pending) are NOT errors and only ride in
        # the `recovery`/completed frame.
        if outcome is RunOutcome.error:
            self._emit(
                "error",
                {"run_id": run_id, "code": "pipeline_error", "message": message},
                base_version,
            )
        self._emit(
            "recovery",
            {"run_id": run_id, "stage": "completed", "result": result.model_dump(mode="json")},
            resulting_version if resulting_version is not None else base_version,
        )
        return result
