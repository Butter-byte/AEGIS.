"""Deterministic port stand-ins for pipeline-orchestration tests.

NOT implementations of Sahil / Yyash / Hrishi's modules. The crudest possible
fixed-rule stand-ins that let `backend.pipeline.Pipeline` be driven through every
RunOutcome branch without depending on the real engines' threshold values.

Signatures match the Protocols in `backend/pipeline.py`:
    TelemetrySource.derive(state)
    FaultSource.active()
    Diagnoser.diagnose(state, active_faults, telemetry)
    Planner.plan(state, diagnosis)
    Twin.simulate(state, plan)
    SafetyEvaluator.evaluate(before, sim, plan, policy)
"""

from __future__ import annotations

from backend.models.common import new_diagnosis_id, new_plan_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import EdgeStatus, NodeStatus, ViolationLevel
from backend.models.recovery import RecoveryPlan
from backend.models.safety import PolicyConfig, SafetyDecision, Violation
from backend.models.simulation import SimDelta, SimMetrics, SimulationResult
from backend.models.state import NetworkState
from backend.models.telemetry import NodeTelemetry, Telemetry
from backend.network.simulator import apply_action

PROTECTED_NODES = {"N1"}  # scaffold: "protected infrastructure" for the safety-reject test

_DEAD_NODE = {NodeStatus.failed, NodeStatus.quarantined}
_BAD_NODE = _DEAD_NODE | {NodeStatus.degraded}
_DEAD_EDGE = {EdgeStatus.failed}


class FakeTelemetry:
    def derive(self, state: NetworkState) -> Telemetry:
        nodes = list(state.nodes.values())
        active = [n for n in nodes if n.status not in _DEAD_NODE]
        return Telemetry(
            at=utcnow(), based_on_version=state.version,
            network_availability=len(active) / max(len(nodes), 1),
            avg_latency=sum(n.latency_ms for n in nodes) / max(len(nodes), 1),
            max_latency=max((n.latency_ms for n in nodes), default=0.0),
            total_packet_loss=0.0,
            active_nodes=len(active),
            failed_nodes=sum(n.status == NodeStatus.failed for n in nodes),
            quarantined_nodes=sum(n.status == NodeStatus.quarantined for n in nodes),
            congested_edges=sum(e.status == EdgeStatus.congested for e in state.edges),
            failed_edges=sum(e.status == EdgeStatus.failed for e in state.edges),
            per_node={
                nid: NodeTelemetry(cpu=n.cpu_percent, latency=n.latency_ms,
                                   packet_loss=n.packet_loss_percent, status=n.status)
                for nid, n in state.nodes.items()
            },
        )


class FakeFaultInjector:
    def active(self):
        return []


class FakeDiagnoser:
    def diagnose(self, state: NetworkState, active_faults, telemetry) -> Diagnosis:
        bad_nodes = [n.id for n in state.nodes.values() if n.status in _BAD_NODE]
        bad_edges = [e.id for e in state.edges if e.status in _DEAD_EDGE]
        hurt = [s.id for s in state.services.values() if s.host_node in bad_nodes]
        healthy = bool(bad_nodes or bad_edges)
        return Diagnosis(
            id=new_diagnosis_id(), created_at=utcnow(), based_on_version=state.version,
            summary=(f"fault affecting nodes={bad_nodes} edges={bad_edges}" if healthy
                     else "network healthy")[:500],
            suspected_nodes=bad_nodes, suspected_edges=bad_edges, suspected_services=hurt,
            confidence=1.0 if healthy else 0.2,
            rationale=f"availability={telemetry.network_availability:.2f}; {len(hurt)} service(s) affected",
        )


class FakePlanner:
    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        plans: list[RecoveryPlan] = []
        for node_id in diagnosis.suspected_nodes:
            if node_id not in state.nodes:
                continue
            actions: list[dict] = []
            for svc in state.services.values():
                if svc.host_node == node_id:
                    target = next(
                        (n for n in state.nodes
                         if n != node_id and n not in PROTECTED_NODES
                         and state.nodes[n].status == NodeStatus.healthy),
                        None,
                    )
                    if target:
                        actions.append({"type": "migrate_service", "service_id": svc.id, "to_node": target})
            actions.append({"type": "quarantine_node", "node_id": node_id})
            plans.append(self._mk(state, diagnosis, "quarantine + migrate", actions))
        return plans

    def _mk(self, state, diagnosis, label, actions) -> RecoveryPlan:
        return RecoveryPlan(
            id=new_plan_id(), created_at=utcnow(), based_on_version=state.version,
            targets_diagnosis=diagnosis.id, strategy_label=label,
            rationale=f"deterministic fake planner: {label}", actions=actions, source="heuristic",
        )


class UnsafePlanner:
    """Always proposes touching protected infrastructure — for the safety-reject test."""

    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        return [RecoveryPlan(
            id=new_plan_id(), created_at=utcnow(), based_on_version=state.version,
            targets_diagnosis=diagnosis.id, strategy_label="quarantine protected core",
            rationale="deliberately unsafe", actions=[{"type": "quarantine_node", "node_id": "N1"}],
            source="heuristic",
        )]


class FakeTwin:
    def simulate(self, state: NetworkState, plan: RecoveryPlan) -> SimulationResult:
        try:
            simulated = state.model_copy(deep=True)
            for action in plan.actions:
                simulated = apply_action(simulated, action)
        except Exception as exc:  # noqa: BLE001 - stage isolation
            return SimulationResult(
                plan_id=plan.id, based_on_version=state.version, feasible=False,
                infeasible_reason=str(exc), computed_at=utcnow(),
            )
        active = [n for n in simulated.nodes.values() if n.status not in _DEAD_NODE]
        unreachable = [
            s.id for s in simulated.services.values()
            if simulated.nodes[s.host_node].status in _DEAD_NODE
        ]
        metrics = SimMetrics(
            availability=(len(simulated.services) - len(unreachable)) / max(len(simulated.services), 1),
            avg_latency=sum(n.latency_ms for n in active) / max(len(active), 1),
            max_latency=max((n.latency_ms for n in active), default=0.0),
            worst_node_load=max((n.load / n.capacity for n in active), default=0.0),
            unreachable_services=unreachable, path_count=len(simulated.services),
        )
        return SimulationResult(
            plan_id=plan.id, based_on_version=state.version, feasible=not unreachable,
            infeasible_reason=None if not unreachable else f"unreachable: {unreachable}",
            metrics=metrics, delta=SimDelta(availability=0.0, avg_latency=0.0, max_latency=0.0),
            computed_at=utcnow(),
        )


class FakeSafetyGate:
    def evaluate(self, before, simulation, plan, policy: PolicyConfig) -> SafetyDecision:
        violations: list[Violation] = []
        if not simulation.feasible:
            violations.append(Violation(
                rule="twin_infeasible", detail=simulation.infeasible_reason or "infeasible",
                level=ViolationLevel.critical,
            ))
        for action in plan.actions:
            if getattr(action, "node_id", None) in PROTECTED_NODES:
                violations.append(Violation(
                    rule="protected_infrastructure",
                    detail=f"action {action.type} targets protected node {action.node_id}",
                    level=ViolationLevel.critical,
                ))
        approved = not any(v.level == ViolationLevel.critical for v in violations)
        return SafetyDecision(
            plan_id=plan.id, based_on_version=before.version, approved=approved, violations=violations,
            evaluated={"availability": simulation.metrics.availability if simulation.metrics else 0.0},
            policy_version=policy.policy_version, decided_at=utcnow(),
        )
