"""REST contract — shapes and status codes on `integration`.

The runtime is always fully wired (real deterministic engines in AppContext), so
the old `module_not_wired` / 501 scaffolding tests are gone. Response shapes here
track `backend/api/routes.py` as implemented; where that diverges from
docs/BACKEND_SCHEMA.md §8 it is called out in the reconciliation report.
"""

from __future__ import annotations

import pytest

from backend.models.faults import Fault
from backend.models.state import NetworkState


def test_get_network_state_returns_valid_state(wired_client):
    r = wired_client.get("/network/state")
    assert r.status_code == 200
    NetworkState.model_validate(r.json())


def test_reset_is_a_forward_version_bump(wired_client):
    v0 = wired_client.get("/network/state").json()["version"]
    v1 = wired_client.post("/network/reset").json()["version"]
    assert v1 == v0 + 1


def test_telemetry_endpoint_returns_projection(wired_client):
    r = wired_client.get("/telemetry")
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["network_availability"] <= 1.0
    assert "per_node" in body


def test_inject_fault_returns_fault_and_bumps_version(wired_client):
    v0 = wired_client.get("/network/state").json()["version"]
    r = wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
    assert r.status_code == 201
    Fault.model_validate(r.json())
    assert r.json()["type"] == "kill_node"
    assert wired_client.get("/network/state").json()["version"] == v0 + 1


def test_malformed_fault_request_is_422(wired_client):
    r = wired_client.post("/faults", json={"type": "not_a_fault", "target": "N2"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.xfail(
    reason="gap B: FaultInjector.clear raises StateInvariantError (not an AegisError), "
    "so an unknown fault id yields 500 instead of the documented 404 — see report",
    strict=True,
)
def test_clear_unknown_fault_is_404(wired_client):
    r = wired_client.delete("/faults/flt-deadbeef")
    assert r.status_code == 404
