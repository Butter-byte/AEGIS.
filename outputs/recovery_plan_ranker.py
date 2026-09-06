"""Safety-gated scoring and ranking for Aegis recovery plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

RiskLevel = Literal["low", "medium", "high"]
ComplexityLevel = Literal["simple", "moderate", "complex"]

RISK_SCORES = {"low": 100.0, "medium": 60.0, "high": 20.0}
COMPLEXITY_SCORES = {"simple": 100.0, "moderate": 60.0, "complex": 25.0}
WEIGHTS = {
    "downtime": 0.30,
    "risk": 0.25,
    "speed": 0.20,
    "complexity": 0.15,
    "resource_utilization": 0.10,
}


@dataclass
class RecoveryPlanMetrics:
    plan_id: str
    title: str
    expected_downtime_seconds: float
    recovery_time_seconds: float
    risk: RiskLevel
    complexity: ComplexityLevel
    additional_resource_utilization_percent: float
    digital_twin_passed: bool
    safety_policy_passed: bool
    rollback_available: bool


@dataclass
class RankedPlan:
    plan_id: str
    title: str
    eligible: bool
    final_score: float | None
    reason: str
    score_breakdown: dict


def lower_is_better_score(value: float, unacceptable_value: float) -> float:
    """Convert a smaller-is-better value to a 0-100 score."""
    value = max(0.0, min(value, unacceptable_value))
    return round(100.0 * (1.0 - value / unacceptable_value), 2)


def is_eligible(plan: RecoveryPlanMetrics) -> tuple[bool, str]:
    """Reject unsafe or infeasible plans before numeric ranking."""
    if not plan.digital_twin_passed:
        return False, "Rejected: Digital Twin simulation did not pass."
    if not plan.safety_policy_passed:
        return False, "Rejected: Safety Engine policy check did not pass."
    if not plan.rollback_available:
        return False, "Rejected: no rollback plan is available."
    if plan.additional_resource_utilization_percent > 90:
        return False, "Rejected: plan would consume more than 90% of backup resources."
    return True, "Eligible for ranking."


def score_plan(plan: RecoveryPlanMetrics) -> RankedPlan:
    """Score a plan using downtime, risk, speed, complexity, and resource impact."""
    eligible, reason = is_eligible(plan)
    if not eligible:
        return RankedPlan(plan.plan_id, plan.title, False, None, reason, {})

    downtime = lower_is_better_score(plan.expected_downtime_seconds, 600.0)
    speed = lower_is_better_score(plan.recovery_time_seconds, 600.0)
    risk = RISK_SCORES[plan.risk]
    complexity = COMPLEXITY_SCORES[plan.complexity]
    resources = lower_is_better_score(plan.additional_resource_utilization_percent, 100.0)
    final_score = round(
        downtime * WEIGHTS["downtime"]
        + risk * WEIGHTS["risk"]
        + speed * WEIGHTS["speed"]
        + complexity * WEIGHTS["complexity"]
        + resources * WEIGHTS["resource_utilization"],
        2,
    )
    return RankedPlan(
        plan.plan_id, plan.title, True, final_score,
        "Eligible and ranked using downtime, risk, speed, complexity, and resource impact.",
        {
            "downtime_score": downtime,
            "risk_score": risk,
            "speed_score": speed,
            "complexity_score": complexity,
            "resource_utilization_score": resources,
            "weights": WEIGHTS,
        },
    )


def rank_recovery_plans(plans: list[RecoveryPlanMetrics]) -> list[RankedPlan]:
    """Return safe plans first, sorted by descending score; retain rejects for audit."""
    return sorted(
        (score_plan(plan) for plan in plans),
        key=lambda plan: (not plan.eligible, -(plan.final_score or 0)),
    )


if __name__ == "__main__":
    sample_plans = [
        RecoveryPlanMetrics("plan-a", "Shift 25% to backup path", 15, 120, "medium", "moderate", 30, True, True, True),
        RecoveryPlanMetrics("plan-b", "Throttle bulk traffic", 5, 60, "low", "simple", 5, True, True, True),
        RecoveryPlanMetrics("plan-c", "Fail over and restart router", 180, 300, "high", "complex", 40, True, True, True),
    ]
    for plan in rank_recovery_plans(sample_plans):
        print(asdict(plan))
