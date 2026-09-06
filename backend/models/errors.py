"""Error envelope + typed exceptions for the REST boundary.

Source of truth: docs/BACKEND_SCHEMA.md §12.

Every non-2xx REST response is an `ErrorEnvelope`. `AegisError` subclasses carry
their own HTTP status so `backend/api/errors.py` can map them in one place.
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
    """Base for errors that map onto the §12 error envelope."""

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


class ModuleNotWired(AegisError):
    """A teammate module is not implemented yet and no fake is installed.

    TEMPORARY — present only while `backend/{network,telemetry,faults,diagnosis,
    recovery,twin,safety}/` are placeholders. Not part of the frozen §12 table.
    """

    code = "module_not_wired"
    http_status = 501
