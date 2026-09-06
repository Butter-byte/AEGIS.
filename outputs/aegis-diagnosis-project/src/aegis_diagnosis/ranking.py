"""Safety-gated candidate scoring."""

from __future__ import annotations

from .models import RankedPlan, RecoveryPlan

RISK = {"low": 100, "medium": 60, "high": 20}; WEIGHTS = {"downtime": .30, "risk": .25, "speed": .20, "complexity": .15, "resources": .10}

class PlanRanker:
    def rank(self, plans: list[RecoveryPlan]) -> list[RankedPlan]:
        ranked = []
        for plan in plans:
            # Demo estimates: replace with Digital Twin measurements before execution.
            slow = "restart" in plan.title.lower() or "repair" in plan.title.lower() or "replace" in plan.title.lower(); downtime, duration, resources = (180, 300, 40) if slow else (15, 120, 30)
            complexity = 25 if plan.requires_human_approval else 70; score = round((100-downtime/6)*WEIGHTS["downtime"] + RISK[plan.risk]*WEIGHTS["risk"] + (100-duration/6)*WEIGHTS["speed"] + complexity*WEIGHTS["complexity"] + (100-resources)*WEIGHTS["resources"], 2)
            ranked.append(RankedPlan(plan.plan_id, 0, True, score, "Candidate only; requires Digital Twin and Safety Engine approval.", {"downtime_score": round(100-downtime/6,2), "risk_score": RISK[plan.risk], "speed_score": round(100-duration/6,2), "complexity_score": complexity, "resource_score": 100-resources}))
        ranked.sort(key=lambda item: item.final_score or 0, reverse=True)
        return [RankedPlan(item.plan_id, index, item.eligible, item.final_score, item.reason, item.score_breakdown) for index, item in enumerate(ranked, 1)]
