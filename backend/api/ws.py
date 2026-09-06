"""WebSocket endpoint (Vikash).

Source of truth: docs/TRD.md §"WebSocket", docs/BACKEND_SCHEMA.md §11.

  * one `/ws`, broadcast to all connections
  * on connect: one `state` frame (seq 0) with the current NetworkState
  * inbound frames are read and discarded — never a mutation path
  * the Broadcaster owns fan-out; this file is just the socket lifecycle
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    ctx = ws.app.state.ctx
    await ws.accept()
    conn = ctx.broadcaster.register(ws)
    conn.enqueue("state", {"state": ctx.state.get_state().model_dump(mode="json")}, ctx.state.current_version())
    sender = asyncio.create_task(ctx.broadcaster.pump(conn))
    try:
        while True:
            await ws.receive_text()  # inbound ignored
    except WebSocketDisconnect:
        pass
    finally:
        ctx.broadcaster.unregister(conn)
        sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass
