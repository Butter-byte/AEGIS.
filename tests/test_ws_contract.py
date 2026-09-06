"""WebSocket contract — initial state frame, broadcast on mutation, inbound ignored."""

from __future__ import annotations


def test_connect_receives_initial_state_frame(wired_client):
    with wired_client.websocket_connect("/ws") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "state"
    assert frame["seq"] == 0
    assert "state" in frame["payload"]


def test_mutation_is_broadcast(wired_client):
    with wired_client.websocket_connect("/ws") as ws:
        ws.receive_json()  # initial
        wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
        types = {ws.receive_json()["type"] for _ in range(2)}
    assert "state" in types and "fault" in types


def test_inbound_frames_are_ignored(wired_client):
    with wired_client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_text('{"type":"reset"}')  # must not mutate anything
        wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
        # still get exactly the state+fault broadcast, nothing weird
        seen = [ws.receive_json()["type"] for _ in range(2)]
    assert set(seen) == {"state", "fault"}
