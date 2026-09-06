"""Broadcaster — server->client event fan-out (Vikash).

Source of truth: docs/TRD.md §"WebSocket".

Transport-agnostic core so it is unit-testable without a socket. A connection is
anything with an async `send_json`. Each connection has its own bounded queue and
monotonic `seq`; a slow/broken connection never blocks the producer or the others.

`publish()` is synchronous and safe to call from StateManager subscribers and the
pipeline (both run on the event loop, single worker).
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from backend.models.common import utcnow
from backend.models.events import WSEvent


class Connection(Protocol):
    async def send_json(self, data: dict) -> None: ...


class _Conn:
    def __init__(self, ws: Connection, maxsize: int = 256) -> None:
        self.ws = ws
        self.queue: asyncio.Queue[WSEvent] = asyncio.Queue(maxsize=maxsize)
        self.seq = 0

    def enqueue(self, event_type: str, payload: dict[str, Any], version: int | None) -> WSEvent:
        event = WSEvent(type=event_type, seq=self.seq, at=utcnow(), version=version, payload=payload)
        self.seq += 1
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - slow consumer; drop
            pass
        return event


class Broadcaster:
    def __init__(self) -> None:
        self._conns: set[_Conn] = set()

    # --- producer side -------------------------------------------------

    def publish(self, event_type: str, payload: dict[str, Any], version: int | None = None) -> None:
        for conn in list(self._conns):
            conn.enqueue(event_type, payload, version)

    def connection_count(self) -> int:
        return len(self._conns)

    # --- consumer side (used by the /ws endpoint) -------------------

    def register(self, ws: Connection) -> _Conn:
        conn = _Conn(ws)
        self._conns.add(conn)
        return conn

    def unregister(self, conn: _Conn) -> None:
        self._conns.discard(conn)

    async def pump(self, conn: _Conn) -> None:
        """Drain one connection's queue to its socket until cancelled or it dies."""
        try:
            while True:
                event = await conn.queue.get()
                await conn.ws.send_json(event.model_dump(mode="json"))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - socket gone / encode error: stop this pump only
            return
