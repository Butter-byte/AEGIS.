"""SafetyDecision contract — output of safety/ (owned by Hrishi).

Source of truth: docs/BACKEND_SCHEMA.md §6.2.

This module fixes the shape of the decision, the Violation record, and a minimal
PolicyConfig covering the example rules the docs already name. Hrishi owns the
rule implementations, the evaluation, and — critically — the threshold VALUES
(marked TEAM DECISION REQUIRED in BACKEND_SCHEMA.md §10). PolicyConfig may be
extended by the Safety Engine; the pipeline only needs to construct and pass it.
"""

from __future__ import annotations

from pydantic import Field

from .common import PLAN_ID, StrictModel, UtcDatetime
from .enums import ViolationLevel


class Violation(StrictModel):
    rule: str = Field(min_length=1, description="stable rule id, e.g. 'availability_floor'")
    detail: str
    level: ViolationLevel


class SafetyDecision(StrictModel):
    plan_id: str = Field(pattern=PLAN_ID)
    based_on_version: int = Field(ge=0)
    approved: bool
    violations: list[Violation] = Field(default_factory=list)
    evaluated: dict[str, float] = Field(default_factory=dict)
    policy_version: str = Field(min_length=1)
    decided_at: UtcDatetime


class PolicyConfig(StrictModel):
    """Thresholds the Safety Engine evaluates against.

    Values below are SCAFFOLD DEFAULTS — see TEAM DECISION REQUIRED (D2).
    """

    policy_version: str = "p0-scaffold"
    availability_floor: float = Field(default=0.99, ge=0.0, le=1.0)
    max_latency_increase_ratio: float = Field(default=0.20, ge=0.0)
    max_node_load_ratio: float = Field(default=0.90, ge=0.0)
    warnings_block: bool = False
