"""End-to-end architectural pipeline, over HTTP, with fakes for every teammate port.

Proves the integration backbone: fault -> telemetry/state change -> diagnosis ->
plan -> twin -> safety -> execute -> recovered state, all observable over /ws.
The scripted-scenario detail is Sahil/Yyash/Hrishi's; this only exercises Vikash's
wiring.
"""

from __future__ import annotations


def test_happy_path_fault_to_recovery(wired_client):
    # 1. healthy
    s0 = wired_client.get("/network/state").json()
    assert s0["services"]["svc-auth"]["status"] == "running"

    # 2. inject a fault on the node hosting svc-auth
    inj = wired_client.post("/faults", json={"type": "kill_node", "target": "N2"}).json()
    assert inj["state"]["nodes"]["N2"]["status"] == "failed"

    # 3. service degraded/down because its ASSIGNED path is broken
    #    (an alternate path existing must NOT auto-heal it)
    s1 = wired_client.get("/network/state").json()
    assert s1["services"]["svc-auth"]["status"] == "down"

    # 4. telemetry reflects it
    tel = wired_client.get("/telemetry").json()
    assert tel["network_availability"] < 1.0
    assert tel["failed_nodes"] == 1

    # 5. run recovery
    run = wired_client.post("/recovery/run").json()
    assert run["outcome"] == "applied"
    assert run["diagnosis"]["suspected_nodes"] == ["N2"]

    # 6. network recovered
    s2 = wired_client.get("/network/state").json()
    assert s2["services"]["svc-auth"]["status"] == "running"
    assert s2["version"] == run["resulting_version"]


def test_alternate_path_does_not_auto_heal_without_reroute(wired_client):
    """The finalized service-state semantics: status is judged against the
    ASSIGNED path only."""
    wired_client.post("/faults", json={"type": "cut_edge", "target": "N1-N3"})
    s = wired_client.get("/network/state").json()
    # svc-auth path is N2-N1-N3; the N1-N3 hop is cut -> down, even though
    # N2-N1-N4-N3 physically exists.
    assert s["services"]["svc-auth"]["status"] == "down"


def test_ws_stream_carries_the_whole_run(wired_client):
    wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
    with wired_client.websocket_connect("/ws") as ws:
        ws.receive_json()  # initial state frame
        run = wired_client.post("/recovery/run").json()
        assert run["outcome"] == "applied"
        # exact event count for an applied run: started + diagnosis
        # + per-candidate (simulation, safety) + state (from execution) + completed
        n = len(run["candidates"])
        expected = 2 + 2 * n + 2
        seen = [ws.receive_json()["type"] for _ in range(expected)]
    assert {"diagnosis", "simulation", "safety", "recovery", "state"} <= set(seen)
    assert seen[0] == "recovery" and seen[-1] == "recovery"
