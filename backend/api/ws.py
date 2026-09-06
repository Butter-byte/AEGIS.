"""WebSocket broadcast layer.

Source of truth: docs/ARCHITECTURE.md §7, docs/BACKEND_SCHEMA.md §7.

  * broadcast-oriented: every connection gets the same event stream
  * one `state` frame is sent on connect (seq 0)
  * inbound frames are read and discarded — never a mutation path (invariant 12)
  * `publish()` is synchronous and safe to call from StateManager / Pipeline,
    which run on the event loop (single worker). Per-connection asyncio.Queue
    decouples a slow client from the producer.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.models.common import utcnow
from backend.models.ws import WSEvent

router = APIRouter()


class _Conn:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.queue: asyncio.Queue[WSEvent] = asyncio.Queue(maxsize=256)
        self.seq = 0

    def enqueue(self, event_type: str, payload: dict, version: int | None) -> None:
        event = WSEvent(type=event_type, seq=self.seq, at=utcnow(), version=version, payload=payload)
        self.seq += 1
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - slow consumer, drop oldest intent
            pass


class Broadcaster:
    def __init__(self) -> None:
        self._conns: set[_Conn] = set()

    def register(self, ws: WebSocket) -> _Conn:
        conn = _Conn(ws)
        self._conns.add(conn)
        return conn

    def unregister(self, conn: _Conn) -> None:
        self._conns.discard(conn)

    def connection_count(self) -> int:
        return len(self._conns)

    def publish(self, event_type: str, payload: dict, version: int | None = None) -> None:
        for conn in list(self._conns):
            conn.enqueue(event_type, payload, version)


async def _pump(conn: _Conn) -> None:
    """Drain this connection's queue to its socket until cancelled or the socket
    dies. A send failure on one connection never affects the others."""
    try:
        while True:
            event = await conn.queue.get()
            await conn.ws.send_json(event.model_dump(mode="json"))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - socket gone / encode error: stop this pump only
        return


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    ctx = ws.app.state.ctx
    await ws.accept()
    conn = ctx.broadcaster.register(ws)
    conn.enqueue(
        "state",
        {"state": ctx.state.get_state().model_dump(mode="json")},
        ctx.state.current_version(),
    )
    sender = asyncio.create_task(_pump(conn))
    try:
        while True:
            await ws.receive_text()  # inbound ignored (invariant 12)
    except WebSocketDisconnect:
        pass
    finally:
        ctx.broadcaster.unregister(conn)
        sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass
