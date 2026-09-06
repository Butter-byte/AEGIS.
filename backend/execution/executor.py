"""Executor — the ONLY component that applies a recovery plan to live state.

Source of truth: docs/TRD.md §"Execution".

Guarantees (this is the enforcement half of "no AI output touches the network
directly"):
  * refuses a plan without an `approved` SafetyDecision
  * refuses a SafetyDecision whose `plan_id` does not match the plan
  * refuses on version conflict (state moved under us)
  * builds ONE mutation batch: the plan's structural effects + the NetworkModel's
    status recompute against a preview of them, applied via StateManager ONCE
    (single version bump, atomic) — never a partial apply
  * never mutates NetworkState directly; never imports planner or safety logic
"""

from __future__ import annotations

from backend.execution.translate import TranslationError, plan_to_mutations
from backend.models.execution import ExecutionResult
from backend.models.recovery import RecoveryPlan
from backend.models.safety import SafetyDecision
from backend.pipeline.ports import NetworkModel
from backend.state.manager import StateManager
from backend.state.preview import preview


class Executor:
    def __init__(self, state: StateManager, network_model: NetworkModel | None = None) -> None:
        self._state = state
        self._model = network_model

    def apply(self, plan: RecoveryPlan, decision: SafetyDecision) -> ExecutionResult:
        if decision.plan_id != plan.id:
            return ExecutionResult(ok=False, reason="safety decision does not match plan")
        if not decision.approved:
            return ExecutionResult(ok=False, reason="safety decision is not approved")

        current = self._state.current_version()
        if plan.based_on_version != current:
            return ExecutionResult(
                ok=False,
                reason=f"conflict: plan based on version {plan.based_on_version}, current is {current}",
            )
        if decision.based_on_version != current:
            return ExecutionResult(
                ok=False,
                reason=f"conflict: decision based on version {decision.based_on_version}, current is {current}",
            )

        snapshot = self._state.get_state()
        try:
            mutations = plan_to_mutations(plan, snapshot, self._model)
        except TranslationError as exc:
            return ExecutionResult(ok=False, reason=f"action translation failed: {exc}")

        if not mutations:
            return ExecutionResult(ok=False, reason="plan produced no applicable state changes")

        if self._model is not None:
            try:
                mutations = [*mutations, *self._model.recompute_status(preview(snapshot, mutations))]
            except Exception as exc:  # noqa: BLE001
                return ExecutionResult(ok=False, reason=f"status recompute failed: {exc}")

        try:
            new_state = self._state.apply_actions(mutations, reason=f"recovery {plan.id}")
        except Exception as exc:  # noqa: BLE001 - surface any apply failure as a clean result
            return ExecutionResult(ok=False, reason=f"apply failed: {exc}")

        return ExecutionResult(ok=True, resulting_version=new_state.version)
