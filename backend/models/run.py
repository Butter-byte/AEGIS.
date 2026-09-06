"""Recovery-run request/response contracts — the `/recovery/*` endpoints.

Source of truth: docs/BACKEND_SCHEMA.md §10. Owned by the pipeline (Vikash).
"""

from __future__ import annotations

from pydantic import Field

from .common import RUN_ID, StrictModel, UtcDatetime
from .diagnosis import Diagnosis
from .enums import RunOutcome
from .recovery import RecoveryPlan
from .safety import SafetyDecision
from .twin import SimulationResult


class RunRequest(StrictModel):
    auto_apply: bool = True


class PlanRequest(StrictModel):
    diagnosis_id: str | None = Field(default=None, description="null -> diagnose fresh")


class CandidateResult(StrictModel):
    plan: RecoveryPlan
    simulation: SimulationResult
    safety: SafetyDecision


class RecoveryRunResult(StrictModel):
    run_id: str = Field(pattern=RUN_ID)
    based_on_version: int = Field(ge=0)
    outcome: RunOutcome
    message: str
    diagnosis: Diagnosis | None = None
    candidates: list[CandidateResult] = Field(default_factory=list)
    applied_plan_id: str | None = None
    resulting_version: int | None = None
    completed_at: UtcDatetime
