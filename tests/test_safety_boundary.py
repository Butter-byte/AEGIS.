"""The core invariant, enforced: no AI output reaches the network without an
approved SafetyDecision for the current version.
"""

from __future__ import annotations

from backend.models.recovery import RecoveryPlan
from backend.models.safety import SafetyDecision
from backend.state.mutations import set_node
from backend.network.simulator import build_seed
from tests import fixtures


def _decision(plan_id, version, approved):
    return SafetyDecision(
        plan_id=plan_id, based_on_version=version, approved=approved,
        violations=[], evaluated={}, policy_version="p0-scaffold",
        decided_at=fixtures.utcnow(),
    )


def _quarantine_plan(version: int) -> RecoveryPlan:
    return RecoveryPlan(
        id="plan-0000aaaa", created_at=fixtures.utcnow(), based_on_version=version,
        targets_diagnosis="dx-0000aaaa", strategy_label="quarantine", rationale="isolate N2",
        actions=[{"type": "quarantine_node", "node_id": "N2"}], source="heuristic",
    )


def test_executor_refuses_unapproved_decision(executor, state):
    plan = _quarantine_plan(state.current_version())
    r = executor.apply(plan, _decision(plan.id, state.current_version(), approved=False))
    assert not r.ok and "not approved" in r.reason
    assert state.current_version() == 0


def test_executor_refuses_decision_for_a_different_plan(executor, state):
    plan = _quarantine_plan(state.current_version())
    r = executor.apply(plan, _decision("plan-ffffffff", state.current_version(), approved=True))
    assert not r.ok and "does not match" in r.reason
    assert state.current_version() == 0


def test_executor_refuses_stale_plan(executor, state):
    plan = _quarantine_plan(0)
    state.apply_actions([set_node("N1", cpu_percent=30.0)], reason="move version")
    r = executor.apply(plan, _decision(plan.id, 0, approved=True))
    assert not r.ok and "conflict" in r.reason


def test_approved_matching_plan_applies_once(executor, state):
    plan = _quarantine_plan(state.current_version())
    r = executor.apply(plan, _decision(plan.id, state.current_version(), approved=True))
    assert r.ok
    assert r.resulting_version == 1
    assert state.current_version() == 1
    assert state.get_state().nodes["N2"].status.value == "quarantined"


def test_seed_is_structurally_valid():
    build_seed()  # raises if not
