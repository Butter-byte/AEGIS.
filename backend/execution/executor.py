"""Executor — the only component that applies a recovery plan to live state.

Source of truth: docs/TRD.md §2.4 (E1–E6), docs/ARCHITECTURE.md §5.

Guarantees:
  * refuses a plan without an approved SafetyDecision for the *current* version
  * refuses a SafetyDecision whose plan_id does not match the plan
  * refuses on version conflict (state moved under us)
  * translates actions to ONE mutation batch and calls StateManager once
    (single version bump, atomic) — no partial application
  * never mutates NetworkState directly; never imports ai/ or safety/
"""

from __future__ import annotations

from collections.abc import Callable

from backend.models.common import StrictModel
from backend.models.recovery import RecoveryPlan
from backend.models.safety import SafetyDecision
from backend.models.state import NetworkState
from backend.execution.translate import plan_to_mutations
from backend.state.manager import StateManager
from backend.state.mutations import Mutation

Translator = Callable[[RecoveryPlan, NetworkState], list[Mutation]]


class ExecutionResult(StrictModel):
    ok: bool
    resulting_version: int | None = None
    reason: str | None = None


class Executor:
    def __init__(self, state: StateManager, translator: Translator = plan_to_mutations) -> None:
        self._state = state
        self._translate = translator

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

        try:
            mutations = self._translate(plan, self._state.get_state())
        except Exception as exc:  # translation is provisional; treat any failure as non-fatal
            return ExecutionResult(ok=False, reason=f"action translation failed: {exc}")

        if not mutations:
            return ExecutionResult(ok=False, reason="plan produced no applicable state changes")

        try:
            new_state = self._state.apply_actions(mutations, reason=f"recovery {plan.id}")
        except Exception as exc:
            return ExecutionResult(ok=False, reason=f"apply failed: {exc}")

        return ExecutionResult(ok=True, resulting_version=new_state.version)
