from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.context import Ports
from backend.execution.executor import Executor
from backend.main import create_app
from backend.models.faults import FaultRequest
from backend.state.manager import StateManager
from backend.state.mutations import set_active_faults
from backend.state.preview import preview
from backend.state.seed import build_seed
from tests import fakes


def all_fake_ports() -> Ports:
    return Ports(
        network_model=fakes.FakeNetworkModel(),
        telemetry=fakes.FakeTelemetry(),
        faults=fakes.FakeFaultInjector(),
        diagnoser=fakes.FakeDiagnoser(),
        planner=fakes.FakePlanner(),
        twin=fakes.FakeTwin(),
        safety=fakes.FakeSafetyGate(),
    )


def inject_fault(sm: StateManager, injector, model, ftype: str, target: str) -> None:
    """Mirror the /faults route: structural muts + status recompute, one batch."""
    fault, structural = injector.inject(FaultRequest(type=ftype, target=target), sm.get_state())
    structural = [*structural, set_active_faults([f.id for f in injector.active()])]
    batch = [*structural, *model.recompute_status(preview(sm.get_state(), structural))]
    sm.apply_actions(batch, reason=f"fault {fault.id}")


@pytest.fixture
def state() -> StateManager:
    return StateManager(build_seed())


@pytest.fixture
def executor(state: StateManager) -> Executor:
    return Executor(state, network_model=fakes.FakeNetworkModel())


@pytest.fixture
def wired_client() -> TestClient:
    app = create_app(ports=all_fake_ports())
    with TestClient(app) as c:
        yield c


@pytest.fixture
def bare_client() -> TestClient:
    """No teammate ports wired — for testing the module_not_wired path."""
    app = create_app(ports=Ports())
    with TestClient(app) as c:
        yield c
