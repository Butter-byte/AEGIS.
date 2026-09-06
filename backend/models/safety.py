"""Safety Gate contract — output of `backend/safety/` (Hrishi).

Source of truth: docs/BACKEND_SCHEMA.md §8.

The Safety Gate is deterministic: same (state, simulation, plan, policy) always
produce the same `SafetyDecision`. It consumes only structured data — never the
AI's text or reasoning. `approved` is True iff there are no `critical` violations.

This module fixes the decision shape, the `Violation` record, and a `PolicyConfig`
covering the rules the docs name. Rule implementations and the threshold VALUES
(TEAM DECISION D2) are Hrishi's.
"""

from __future__ import annotations

from pydantic import Field

from .common import PLAN_ID, StrictModel, UtcDatetime
from .enums import ViolationLevel


class Violation(StrictModel):
    rule: str = Field(min_length=1, description="stable rule id, e.g. 'availability_floor'")
    detail: str = Field(min_length=1, description="human-readable")
    level: ViolationLevel


class SafetyDecision(StrictModel):
    plan_id: str = Field(pattern=PLAN_ID)
    based_on_version: int = Field(ge=0)
    approved: bool = Field(description="True iff no critical violations")
    violations: list[Violation] = Field(default_factory=list)
    evaluated: dict[str, float] = Field(default_factory=dict, description="metric values the decision used")
    policy_version: str = Field(min_length=1)
    decided_at: UtcDatetime


class PolicyConfig(StrictModel):
    """Thresholds the Safety Gate evaluates against.

    Values here are SCAFFOLD DEFAULTS (TEAM DECISION D2 — owned by Hrishi).
    """

    policy_version: str = "p0-scaffold"
    availability_floor: float = Field(default=0.99, ge=0.0, le=1.0)
    max_latency_increase_ratio: float = Field(default=0.20, ge=0.0)
    max_node_load_ratio: float = Field(default=0.90, ge=0.0)
    warnings_block: bool = False
