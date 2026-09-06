"""AEGIS backend app assembly.

Run: `uvicorn backend.main:app --workers 1`
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import errors, routes, ws
from backend.api.context import AppContext


def create_app() -> FastAPI:
    app = FastAPI(title="AEGIS", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
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
