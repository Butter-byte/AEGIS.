"""Pipeline orchestration — stage order, WS events, and every RunOutcome branch."""

from __future__ import annotations

from backend.models.enums import RunOutcome
from backend.pipeline.orchestrator import Pipeline
from backend.state.manager import StateManager
from backend.state.seed import build_seed
from tests import fakes
from tests.conftest import inject_fault


def _events():
    log: list[tuple[str, dict]] = []
    return log, (lambda t, p, v: log.append((t, p)))


def _pipeline(sm, publisher=None, planner=None):
    return Pipeline(
        state=sm,
        network_model=fakes.FakeNetworkModel(),
        telemetry=fakes.FakeTelemetry(),
        faults=fakes.FakeFaultInjector(),
        diagnoser=fakes.FakeDiagnoser(),
        planner=planner or fakes.FakePlanner(),
        twin=fakes.FakeTwin(),
        safety=fakes.FakeSafetyGate(),
        publisher=publisher,
    )


def test_healthy_network_produces_no_plan():
    sm = StateManager(build_seed())
    result = _pipeline(sm).run()
    assert result.outcome == RunOutcome.no_plan
    assert sm.current_version() == 0


def test_full_run_emits_events_in_order_and_applies():
    sm = StateManager(build_seed())
    model, inj = fakes.FakeNetworkModel(), fakes.FakeFaultInjector()
    inject_fault(sm, inj, model, "kill_node", "N2")
    assert sm.get_state().services["svc-auth"].status == "down"

    log, pub = _events()
    result = _pipeline(sm, publisher=pub).run()

    assert result.outcome == RunOutcome.applied
    assert result.resulting_version == sm.current_version()
    assert sm.get_state().services["svc-auth"].status == "running"
    order = [t for t, _ in log]
    assert order[0] == "recovery"
    assert order.index("diagnosis") < order.index("simulation") < order.index("safety")
    assert order[-1] == "recovery"


def test_unsafe_plan_is_rejected_and_nothing_mutates():
    sm = StateManager(build_seed())
    model, inj = fakes.FakeNetworkModel(), fakes.FakeFaultInjector()
    inject_fault(sm, inj, model, "kill_node", "N2")
    v_before = sm.current_version()

    result = _pipeline(sm, planner=fakes.UnsafePlanner()).run()

    assert result.outcome == RunOutcome.no_safe_plan
    assert sm.current_version() == v_before
    assert any(v.rule == "protected_infrastructure"
               for c in result.candidates for v in c.safety.violations)


def test_approved_pending_when_auto_apply_false():
    sm = StateManager(build_seed())
    model, inj = fakes.FakeNetworkModel(), fakes.FakeFaultInjector()
    inject_fault(sm, inj, model, "kill_node", "N2")
    v_before = sm.current_version()

    result = _pipeline(sm).run(auto_apply=False)
    assert result.outcome == RunOutcome.approved_pending
    assert sm.current_version() == v_before


def test_unwired_modules_give_error_outcome():
    sm = StateManager(build_seed())
    assert Pipeline(state=sm).run().outcome == RunOutcome.error
