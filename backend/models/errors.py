"""Error envelope + typed exceptions.

Source of truth: docs/BACKEND_SCHEMA.md §9.

`not_implemented` (HTTP 501) is a TEMPORARY scaffolding code used while teammate
modules are stubbed. It is not in the frozen §9 table and should disappear once
telemetry / faults / ai / twin / safety are wired. Flagged in the Phase 0/1
report as a schema addition to ratify or remove.
"""

from __future__ import annotations

from .common import StrictModel


class ErrorBody(StrictModel):
    code: str
    message: str
    details: dict | None = None


class ErrorEnvelope(StrictModel):
    error: ErrorBody


class AegisError(Exception):
    """Base for errors that map cleanly onto the §9 error envelope."""

    code = "internal_error"
    http_status = 500

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(error=ErrorBody(code=self.code, message=self.message, details=self.details))


class RequestValidationFailed(AegisError):
    code = "validation_error"
    http_status = 422


class InvalidFault(AegisError):
    code = "invalid_fault"
    http_status = 422


class InvalidTarget(AegisError):
    code = "invalid_target"
    http_status = 404


class NotFound(AegisError):
    code = "not_found"
    http_status = 404


class Conflict(AegisError):
    code = "conflict"
    http_status = 409


class PipelineError(AegisError):
    code = "pipeline_error"
    http_status = 502


class ExecutionFailed(AegisError):
    code = "execution_error"
    http_status = 500


class InternalError(AegisError):
    code = "internal_error"
    http_status = 500


class NotImplementedYet(AegisError):
    """TEMPORARY — teammate module not wired yet (see module docstring)."""

    code = "not_implemented"
    http_status = 501
