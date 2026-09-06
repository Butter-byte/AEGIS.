"""Maps exceptions to the §9 error envelope.

Source of truth: docs/BACKEND_SCHEMA.md §9.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.models.errors import AegisError, ErrorBody, ErrorEnvelope


def _envelope(code: str, message: str, details: dict | None = None) -> dict:
    return ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details)).model_dump(mode="json")


def install(app: FastAPI) -> None:
    @app.exception_handler(AegisError)
    async def _aegis(_: Request, exc: AegisError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.envelope().model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validation_error",
                "request failed schema validation",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", f"{type(exc).__name__}: {exc}"),
        )
