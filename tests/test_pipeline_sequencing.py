"""Pipeline orchestration — stage order, WS events, and every RunOutcome branch.

Uses `tests/fakes.py` stand-ins so each branch is reached deterministically,
independent of the real engines' threshold values. The end-to-end wiring with
the real engines is covered by tests/test_e2e_pipeline.py.
"""

from __future__ import annotations

from backend.models.enums import NodeStatus, RunOutcome
from backend.pipeline import Pipeline
from backend.state.manager import StateManager
from backend.state.mutations import set_node
from backend.network.simulator import build_seed
from tests import fakes


def _events():
    log: list[tuple[str, dict]] = []
    return log, (lambda t, p, v: log.append((t, p)))


def _pipeline(sm, publisher=None, planner=None):
    return Pipeline(
        state=sm,
        telemetry=fakes.FakeTelemetry(),
        faults=fakes.FakeFaultInjector(),
        diagnoser=fakes.FakeDiagnoser(),
        planner=planner or fakes.FakePlanner(),
        twin=fakes.FakeTwin(),
        safety=fakes.FakeSafetyGate(),
        publisher=publisher,
    )


def _break_node(sm: StateManager, node_id: str) -> None:
    sm.apply_actions([set_node(node_id, status=NodeStatus.failed.value)], reason="test fault")


def test_healthy_network_produces_no_plan():
    sm = StateManager(build_seed())
    result = _pipeline(sm).run()
    assert result.outcome == RunOutcome.no_plan
    assert sm.current_version() == 0


def test_full_run_emits_events_in_order_and_applies():
    sm = StateManager(build_seed())
    _break_node(sm, "N2")
    v_after_fault = sm.current_version()

    log, pub = _events()
    result = _pipeline(sm, publisher=pub).run()

    assert result.outcome == RunOutcome.applied
    assert result.resulting_version == sm.current_version() > v_after_fault
    assert sm.get_state().nodes["N2"].status == NodeStatus.quarantined
    order = [t for t, _ in log]
    assert order[0] == "recovery"
    assert order.index("diagnosis") < order.index("simulation") < order.index("safety")
    assert order[-1] == "recovery"


def test_unsafe_plan_is_rejected_and_nothing_mutates():
    sm = StateManager(build_seed())
    _break_node(sm, "N2")
    v_before = sm.current_version()

    result = _pipeline(sm, planner=fakes.UnsafePlanner()).run()

    assert result.outcome == RunOutcome.no_safe_plan
    assert sm.current_version() == v_before
    assert any(v.rule == "protected_infrastructure"
               for c in result.candidates for v in c.safety.violations)


def test_approved_pending_when_auto_apply_false():
    sm = StateManager(build_seed())
    _break_node(sm, "N2")
    v_before = sm.current_version()

    result = _pipeline(sm).run(auto_apply=False)
    assert result.outcome == RunOutcome.approved_pending
    assert sm.current_version() == v_before


def test_unwired_modules_give_error_outcome():
    sm = StateManager(build_seed())
    assert Pipeline(state=sm).run().outcome == RunOutcome.error
