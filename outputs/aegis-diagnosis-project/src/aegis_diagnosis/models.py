"""Typed domain objects shared by all pipeline stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["warning", "critical"]
Confidence = Literal["low", "medium", "high"]
Risk = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Finding:
    anomaly_type: str
    severity: Severity
    target_id: str
    observed_value: float | str
    threshold: float | str | None
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hypothesis:
    diagnosis_id: str
    root_cause: str
    confidence_score: float
    confidence: Confidence
    affected_targets: list[str]
    explanation: str
    supporting_evidence: list[str]
    next_checks: list[str]
    contradicting_evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecoveryPlan:
    plan_id: str
    diagnosis_id: str
    title: str
    objective: str
    rationale: str
    risk: Risk
    requires_human_approval: bool
    actions: list[dict[str, Any]]
    preconditions: list[str]
    verification: list[str]
    stop_conditions: list[str]
    rollback: list[dict[str, Any]]


@dataclass(frozen=True)
class RankedPlan:
    plan_id: str
    rank: int
    eligible: bool
    final_score: float | None
    reason: str
    score_breakdown: dict[str, float] = field(default_factory=dict)


def to_json(value: Any) -> Any:
    """Convert domain objects to JSON-safe dictionaries recursively."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_json(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    return value
