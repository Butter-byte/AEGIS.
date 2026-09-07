"""End-to-end pipeline over HTTP against the real wired engines.

Proves the integration backbone on `integration`: fault -> node-status change ->
telemetry reflects it -> POST /recovery/run diagnoses, simulates, safety-gates,
executes, and bumps the live version, all observable over /ws.

NOTE: on `integration` the fault path does NOT recompute *service* status from
topology (see the "service status recompute" gap in the reconciliation report),
so these assertions track *node* status + telemetry + the run outcome, which are
the parts of the flow that are actually wired.
"""

from __future__ import annotations


def test_happy_path_fault_to_recovery(wired_client):
    s0 = wired_client.get("/network/state").json()
    assert s0["nodes"]["N2"]["status"] == "healthy"
    base_version = s0["version"]

    # inject a fault on the node hosting svc-auth
    fault = wired_client.post("/faults", json={"type": "kill_node", "target": "N2"}).json()
    assert fault["type"] == "kill_node" and fault["target"] == "N2"

    s1 = wired_client.get("/network/state").json()
    assert s1["nodes"]["N2"]["status"] == "failed"
    assert s1["version"] == base_version + 1
    assert "N2" in s1["active_fault_ids"] or fault["id"] in s1["active_fault_ids"]

    # telemetry reflects it
    tel = wired_client.get("/telemetry").json()
    assert tel["network_availability"] < 1.0
    assert tel["failed_nodes"] == 1

    # run recovery
    run = wired_client.post("/recovery/run").json()
    assert run["outcome"] == "applied"
    assert run["diagnosis"]["suspected_nodes"] == ["N2"]
    assert run["applied_plan_id"] is not None

    # live state advanced and the affected node was isolated by the applied plan
    s2 = wired_client.get("/network/state").json()
    assert s2["version"] == run["resulting_version"] > s1["version"]
    assert s2["nodes"]["N2"]["status"] == "quarantined"


def test_recovery_run_on_healthy_network_finds_no_plan(wired_client):
    run = wired_client.post("/recovery/run").json()
    assert run["outcome"] in {"no_plan", "diagnosis_failed"}
    assert wired_client.get("/network/state").json()["version"] == 0


def test_reset_returns_network_to_baseline(wired_client):
    wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
    wired_client.post("/faults", json={"type": "congest_edge", "target": "N1-N2"})

    degraded = wired_client.get("/network/state").json()
    assert degraded["nodes"]["N2"]["status"] == "failed"
    assert any(e["status"] != "active" for e in degraded["edges"])
    assert degraded["active_fault_ids"]
    assert wired_client.get("/faults").json()  # tracker has entries

    wired_client.post("/network/reset")

    s = wired_client.get("/network/state").json()
    assert all(n["status"] == "healthy" for n in s["nodes"].values())
    assert all(e["status"] == "active" for e in s["edges"])
    assert s["active_fault_ids"] == []
    assert wired_client.get("/faults").json() == []  # FaultInjector tracker cleared


def test_repeated_recovery_cycle(wired_client):
    for _ in range(2):
        wired_client.post("/network/reset")

        base = wired_client.get("/network/state").json()
        assert all(n["status"] == "healthy" for n in base["nodes"].values())
        assert base["active_fault_ids"] == []

        wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
        run = wired_client.post("/recovery/run").json()
        assert run["outcome"] == "applied"
        assert run["applied_plan_id"] is not None
        assert wired_client.get("/network/state").json()["nodes"]["N2"]["status"] == "quarantined"


def test_ws_stream_carries_the_whole_run(wired_client):
    wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
    with wired_client.websocket_connect("/ws") as ws:
        ws.receive_json()  # initial state frame
        run = wired_client.post("/recovery/run").json()
        assert run["outcome"] == "applied"
        # started + diagnosis + per-candidate (simulation, safety) + state + completed
        n = len(run["candidates"])
        expected = 2 + 2 * n + 2
        seen = [ws.receive_json()["type"] for _ in range(expected)]
    assert {"diagnosis", "simulation", "safety", "recovery", "state"} <= set(seen)
    assert seen[0] == "recovery" and seen[-1] == "recovery"
