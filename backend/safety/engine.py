from __future__ import annotations

from backend.models.common import utcnow
from backend.models.enums import ViolationLevel
from backend.models.recovery import RecoveryPlan
from backend.models.safety import PolicyConfig, SafetyDecision, Violation
from backend.models.simulation import SimulationResult
from backend.models.state import NetworkState


class SafetyEngine:
    def evaluate(self, before: NetworkState, sim: SimulationResult, plan: RecoveryPlan, policy: PolicyConfig) -> SafetyDecision:
        violations: list[Violation] = []
        metrics = sim.metrics
        if not sim.feasible or metrics is None:
            violations.append(Violation(rule="twin_feasibility", detail=sim.infeasible_reason or "simulation was infeasible", level=ViolationLevel.critical))
        else:
            if metrics.availability < policy.availability_floor:
                violations.append(Violation(rule="availability_floor", detail=f"availability {metrics.availability:.3f} below {policy.availability_floor:.3f}", level=ViolationLevel.critical))
            if metrics.unreachable_services:
                violations.append(Violation(rule="service_reachability", detail=f"unreachable services: {metrics.unreachable_services}", level=ViolationLevel.critical))
            if metrics.worst_node_load > policy.max_node_load_ratio:
                violations.append(Violation(rule="node_load_limit", detail=f"worst load ratio {metrics.worst_node_load:.3f} above {policy.max_node_load_ratio:.3f}", level=ViolationLevel.critical))
        return SafetyDecision(plan_id=plan.id, based_on_version=before.version, approved=not any(v.level == ViolationLevel.critical for v in violations), violations=violations, evaluated={"availability": metrics.availability if metrics else 0.0}, policy_version=policy.policy_version, decided_at=utcnow())