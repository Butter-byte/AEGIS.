"""WebSocket contract — initial state frame, broadcast on mutation, inbound ignored.

On `integration` the broadcaster emits a `state` frame on connect and after every
committed StateManager mutation. There is no dedicated `fault` frame (the fault
route mutates state, which triggers the `state` broadcast) — noted in the report.
"""

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
        frame = ws.receive_json()
    assert frame["type"] == "state"
    assert frame["payload"]["state"]["nodes"]["N2"]["status"] == "failed"


def test_inbound_frames_are_ignored(wired_client):
    with wired_client.websocket_connect("/ws") as ws:
        ws.receive_json()  # initial
        ws.send_text('{"type":"reset"}')  # must not mutate anything
        wired_client.post("/faults", json={"type": "kill_node", "target": "N2"})
        frame = ws.receive_json()
    assert frame["type"] == "state"
    assert frame["payload"]["state"]["version"] == 1  # exactly one mutation happened
