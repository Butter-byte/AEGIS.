"""Shared test fixtures, aligned to the `integration` composition root.

The runtime wires real deterministic engines in `AppContext.build()` (no `Ports`
container, no `create_app(ports=...)`, no teammate stubs). Tests exercise that
same wiring; `tests/fakes.py` supplies stand-ins only where a test needs to force
a specific pipeline branch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.execution.executor import Executor
from backend.faults.injector import FaultInjector
from backend.main import create_app
from backend.models.faults import FaultRequest
from backend.network.simulator import build_seed
from backend.state.manager import StateManager


def inject_fault(injector: FaultInjector, ftype: str, target: str):
    """Inject a fault through the real FaultInjector (mirrors POST /faults)."""
    return injector.inject(FaultRequest(type=ftype, target=target))


@pytest.fixture
def state() -> StateManager:
    return StateManager(build_seed())


@pytest.fixture
def executor(state: StateManager) -> Executor:
    return Executor(state)


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


# `wired_client` kept as an alias: the runtime is always fully wired now.
@pytest.fixture
def wired_client(client: TestClient) -> TestClient:
    return client
