"""AEGIS backend app assembly.

Run: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1`
(exactly one worker — the live NetworkState is in process memory).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import errors, routes, ws
from backend.api.context import AppContext

# Comma-separated list of allowed browser origins. Default keeps the Vite dev
# server working with no configuration; containers pass AEGIS_CORS_ORIGINS.
_DEFAULT_CORS_ORIGINS = "http://localhost:5173"


def _cors_origins() -> list[str]:
    raw = os.getenv("AEGIS_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="AEGIS", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.ctx = AppContext.build()
    errors.install(app)
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


app = create_app()
