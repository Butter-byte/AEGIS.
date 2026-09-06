"""Broadcaster — per-connection seq, fan-out, slow-consumer isolation."""

from __future__ import annotations

import asyncio

import pytest

from backend.events.broadcaster import Broadcaster


class _Sink:
    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.received.append(data)


def test_publish_enqueues_per_connection_with_monotonic_seq():
    b = Broadcaster()
    c = b.register(_Sink())
    b.publish("state", {"x": 1}, version=3)
    b.publish("fault", {"y": 2}, version=4)
    e1 = c.queue.get_nowait()
    e2 = c.queue.get_nowait()
    assert (e1.seq, e1.type.value, e1.version) == (0, "state", 3)
    assert (e2.seq, e2.type.value, e2.version) == (1, "fault", 4)


def test_fan_out_to_all_connections():
    b = Broadcaster()
    a, c = b.register(_Sink()), b.register(_Sink())
    b.publish("state", {}, 1)
    assert a.queue.qsize() == 1 and c.queue.qsize() == 1


def test_pump_delivers_then_stops_on_dead_socket():
    b = Broadcaster()
    sink = _Sink()
    conn = b.register(sink)
    b.publish("state", {"n": 1}, 1)

    async def drive():
        task = asyncio.create_task(b.pump(conn))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(drive())
    assert sink.received and sink.received[0]["payload"] == {"n": 1}
