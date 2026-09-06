"""REST contract — shapes, status codes, and the module_not_wired path."""

from __future__ import annotations

from backend.models.state import NetworkState


def test_get_network_state_returns_valid_state(wired_client):
    r = wired_client.get("/network/state")
    assert r.status_code == 200
    NetworkState.model_validate(r.json())


def test_reset_is_a_forward_version_bump(wired_client):
    v0 = wired_client.get("/network/state").json()["version"]
    v1 = wired_client.post("/network/reset").json()["version"]
    assert v1 == v0 + 1


def test_unwired_telemetry_returns_501(bare_client):
    r = bare_client.get("/telemetry")
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "module_not_wired"


def test_unwired_recovery_run_reports_error_outcome_not_500(bare_client):
    r = bare_client.post("/recovery/run")
    assert r.status_code == 200
    assert r.json()["outcome"] == "error"


def test_inject_fault_shape_and_version_bump(wired_client):
    v0 = wired_client.get("/network/state").json()["version"]
    r = wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
    assert r.status_code == 201
    body = r.json()
    assert body["fault"]["type"] == "kill_node"
    assert body["state"]["version"] == v0 + 1


def test_malformed_fault_request_is_422(wired_client):
    r = wired_client.post("/faults", json={"type": "not_a_fault", "target": "N2"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_clear_unknown_fault_is_404(wired_client):
    r = wired_client.delete("/faults/flt-deadbeef")
    assert r.status_code == 404
