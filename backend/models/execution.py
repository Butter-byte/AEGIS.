"""Execution result contract — output of `backend/execution/` (Vikash).

Source of truth: docs/BACKEND_SCHEMA.md §9.

Execution is the ONLY authoritative mutation path for a recovery. It refuses any
plan without an `approved` SafetyDecision for the current state version, then
applies the plan's actions as ONE atomic mutation batch via StateManager.
"""

from __future__ import annotations

from pydantic import Field

from .common import StrictModel


class ExecutionResult(StrictModel):
    ok: bool
    resulting_version: int | None = None
    reason: str | None = Field(default=None, description="set iff ok is False")
