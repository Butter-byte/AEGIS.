"""AEGIS backend app assembly (Vikash).

Run: `uvicorn backend.main:app --workers 1 --port 8000`

The composition root. It wires teammate modules into `Ports` as they land:

    from backend.network import RealSeedSource        # Sahil
    from backend.telemetry import RealTelemetry       # Sahil
    ...
    ports = Ports(seed_source=RealSeedSource(), telemetry=RealTelemetry(), ...)

Until then every teammate port is None and the matching endpoints return
`module_not_wired` (501). `GET /network/state`, `POST /network/reset` and `/ws`
work now, against the scaffold seed.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.api import errors, routes, ws
from backend.api.context import AppContext, Ports


def create_app(ports: Ports | None = None) -> FastAPI:
    app = FastAPI(title="AEGIS", version="0.1.0")
    app.state.ctx = AppContext.build(ports=ports)
    errors.install(app)
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


app = create_app()
