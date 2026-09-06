"""Deterministic fakes for every teammate port (Vikash test infrastructure).

NOT implementations of Sahil / Yyash / Hrishi's modules — the crudest possible
stand-ins that let the integration layer be exercised end to end: fixed rules, no
randomness, no cleverness. A real module replaces the matching fake in the
composition root; the pipeline does not change.
"""

from __future__ import annotations

from collections import deque

from backend.models.common import new_diagnosis_id, new_fault_id, new_plan_id, new_sim_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import EdgeStatus, FaultType, NodeStatus, ServiceStatus
from backend.models.faults import Fault, FaultRequest
from backend.models.recovery import RecoveryPlan
from backend.models.safety import PolicyConfig, SafetyDecision, Violation
from backend.models.state import NetworkState
from backend.models.twin import SimDelta, SimMetrics, SimulationResult
from backend.state.mutations import Mutation, set_edge, set_node, set_service

PROTECTED_NODES = {"N1"}  # scaffold: N1 is "protected infrastructure" for the safety demo

_DEAD_NODE = {NodeStatus.failed, NodeStatus.quarantined}
_DEAD_EDGE = {EdgeStatus.failed}


def _service_status(state: NetworkState, svc) -> ServiceStatus:
    """Status judged against the ASSIGNED path only — never re-routes."""
    if not svc.path:
        return ServiceStatus.down
    edge_by_pair = {frozenset((e.source, e.target)): e for e in state.edges}
    for hop in svc.path:
        if state.nodes[hop].status in _DEAD_NODE:
            return ServiceStatus.down
    for a, b in zip(svc.path, svc.path[1:]):
        e = edge_by_pair.get(frozenset((a, b)))
        if e is None or e.status in _DEAD_EDGE:
            return ServiceStatus.down
    degraded = any(state.nodes[h].status == NodeStatus.degraded for h in svc.path) or any(
        edge_by_pair[frozenset((a, b))].status == EdgeStatus.congested
        for a, b in zip(svc.path, svc.path[1:])
    )
    return ServiceStatus.degraded if degraded else ServiceStatus.running


# --------------------------------------------------------------------------
# Sahil: NetworkModel  (status recompute + path resolution)
# --------------------------------------------------------------------------

class FakeNetworkModel:
    def recompute_status(self, state: NetworkState) -> list[Mutation]:
        out: list[Mutation] = []
        for svc in state.services.values():
            want = _service_status(state, svc)
            if want != svc.status:
                out.append(set_service(svc.id, status=want.value))
        return out

    def resolve_path(self, service_id, state, *, avoid_nodes=None, avoid_edges=None, new_host=None):
        avoid_nodes = set(avoid_nodes or [])
        avoid_edges = set(avoid_edges or [])
        svc = state.services[service_id]
        src = new_host or svc.host_node
        dst = svc.path[-1] if svc.path else next((n for n in state.nodes if n != src), None)
        if dst is None or dst == src:
            return [src]
        adj: dict[str, list[str]] = {}
        for e in state.edges:
            if e.status in _DEAD_EDGE or e.id in avoid_edges:
                continue
            for a, b in ((e.source, e.target), (e.target, e.source)):
                if a in avoid_nodes or b in avoid_nodes:
                    continue
                if state.nodes[a].status in _DEAD_NODE or state.nodes[b].status in _DEAD_NODE:
                    continue
                adj.setdefault(a, []).append(b)
        prev = {src: src}
        q = deque([src])
        while q:
            cur = q.popleft()
            if cur == dst:
                break
            for nxt in adj.get(cur, []):
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        if dst not in prev:
            return None
        path = [dst]
        while path[-1] != src:
            path.append(prev[path[-1]])
        return list(reversed(path))


# --------------------------------------------------------------------------
# Sahil: telemetry + faults
# --------------------------------------------------------------------------

class FakeTelemetry:
    def derive(self, state: NetworkState):
        from backend.models.telemetry import NodeTelemetry, Telemetry

        running = sum(1 for s in state.services.values() if s.status == ServiceStatus.running)
        total = len(state.services) or 1
        return Telemetry(
            at=utcnow(), based_on_version=state.version,
            network_availability=running / total,
            avg_latency=sum(n.latency_ms for n in state.nodes.values()) / len(state.nodes),
            max_latency=max((n.latency_ms for n in state.nodes.values()), default=0.0),
            total_packet_loss=0.0,
            active_nodes=sum(1 for n in state.nodes.values() if n.status in {NodeStatus.healthy, NodeStatus.degraded}),
            failed_nodes=sum(1 for n in state.nodes.values() if n.status == NodeStatus.failed),
            quarantined_nodes=sum(1 for n in state.nodes.values() if n.status == NodeStatus.quarantined),
            congested_edges=sum(1 for e in state.edges if e.status == EdgeStatus.congested),
            failed_edges=sum(1 for e in state.edges if e.status == EdgeStatus.failed),
            per_node={
                nid: NodeTelemetry(cpu_percent=n.cpu_percent, latency_ms=n.latency_ms,
                                   packet_loss_percent=n.packet_loss_percent, status=n.status)
                for nid, n in state.nodes.items()
            },
        )


class FakeFaultInjector:
    def __init__(self) -> None:
        self._active: dict[str, Fault] = {}

    def active(self) -> list[Fault]:
        return list(self._active.values())

    def inject(self, request: FaultRequest, state: NetworkState) -> tuple[Fault, list[Mutation]]:
        fault = Fault(id=new_fault_id(), type=request.type, target=request.target,
                      params=request.params or {}, created_at=utcnow())
        self._active[fault.id] = fault
        return fault, self._structural(request.type, request.target, clearing=False)

    def clear(self, fault_id: str, state: NetworkState) -> list[Mutation]:
        fault = self._active.pop(fault_id)
        return self._structural(fault.type, fault.target, clearing=True)

    @staticmethod
    def _structural(ftype: FaultType, target: str, *, clearing: bool) -> list[Mutation]:
        if ftype in {FaultType.kill_node, FaultType.degrade_node, FaultType.overload_node}:
            status = NodeStatus.healthy if clearing else (
                NodeStatus.failed if ftype == FaultType.kill_node else NodeStatus.degraded
            )
            return [set_node(target, status=status.value)]
        if ftype in {FaultType.cut_edge, FaultType.congest_edge}:
            status = EdgeStatus.active if clearing else (
                EdgeStatus.failed if ftype == FaultType.cut_edge else EdgeStatus.congested
            )
            return [set_edge(target, status=status.value)]
        return []


# --------------------------------------------------------------------------
# Yyash: diagnosis + planner
# --------------------------------------------------------------------------

class FakeDiagnoser:
    def diagnose(self, state: NetworkState, telemetry, active_faults) -> Diagnosis:
        bad_nodes = [n.id for n in state.nodes.values() if n.status in _DEAD_NODE]
        bad_edges = [e.id for e in state.edges if e.status in _DEAD_EDGE]
        hurt = [s.id for s in state.services.values() if s.status != ServiceStatus.running]
        summary = "network healthy" if not (bad_nodes or bad_edges) else (
            f"fault affecting nodes={bad_nodes} edges={bad_edges}"
        )
        return Diagnosis(
            id=new_diagnosis_id(), created_at=utcnow(), based_on_version=state.version,
            summary=summary[:500], suspected_nodes=bad_nodes, suspected_edges=bad_edges,
            suspected_services=hurt, confidence=1.0 if (bad_nodes or bad_edges) else 0.2,
            rationale=f"availability={telemetry.network_availability:.2f}; {len(hurt)} service(s) not running",
            source="mock",
        )


class FakePlanner:
    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        plans: list[RecoveryPlan] = []
        for node_id in diagnosis.suspected_nodes:
            actions = [{"type": "quarantine_node", "node_id": node_id}]
            for svc in state.services.values():
                if svc.host_node == node_id:
                    target = next(
                        (n for n in state.nodes if n != node_id and n not in PROTECTED_NODES), None
                    )
                    if target:
                        actions.append({"type": "migrate_service", "service_id": svc.id, "to_node": target})
            plans.append(self._mk(state, diagnosis, "quarantine + migrate", actions))
        for edge_id in diagnosis.suspected_edges:
            hurt = [s.id for s in state.services.values()
                    if _edge_on_path(edge_id, s.path, state) and s.status != ServiceStatus.running]
            actions = [{"type": "reroute", "service_id": sid, "avoid_edges": [edge_id]} for sid in hurt]
            if actions:
                plans.append(self._mk(state, diagnosis, "reroute around link", actions))
        return plans

    def _mk(self, state, diagnosis, label, actions) -> RecoveryPlan:
        return RecoveryPlan(
            id=new_plan_id(), created_at=utcnow(), based_on_version=state.version,
            targets_diagnosis=diagnosis.id, strategy_label=label,
            rationale=f"deterministic fake planner: {label}", actions=actions, source="mock",
        )


class UnsafePlanner:
    """Always proposes touching protected infrastructure — for the safety-reject test."""

    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        return [RecoveryPlan(
            id=new_plan_id(), created_at=utcnow(), based_on_version=state.version,
            targets_diagnosis=diagnosis.id, strategy_label="quarantine protected core",
            rationale="deliberately unsafe", actions=[{"type": "quarantine_node", "node_id": "N1"}],
            source="mock",
        )]


def _edge_on_path(edge_id: str, path: list[str], state: NetworkState) -> bool:
    ids = {frozenset((e.source, e.target)): e.id for e in state.edges}
    return any(ids.get(frozenset((a, b))) == edge_id for a, b in zip(path, path[1:]))


# --------------------------------------------------------------------------
# Sahil: Digital Twin
# --------------------------------------------------------------------------

class FakeTwin:
    def __init__(self) -> None:
        self._model = FakeNetworkModel()

    def validate(self, state_copy: NetworkState, plan: RecoveryPlan) -> SimulationResult:
        from backend.execution.translate import TranslationError, plan_to_mutations
        from backend.state.preview import preview

        try:
            muts = plan_to_mutations(plan, state_copy, self._model)
        except TranslationError as exc:
            return SimulationResult(
                id=new_sim_id(), plan_id=plan.id, based_on_version=state_copy.version,
                feasible=False, infeasible_reason=str(exc), computed_at=utcnow(),
            )
        muts = [*muts, *self._model.recompute_status(preview(state_copy, muts))]
        predicted = preview(state_copy, muts)
        running = sum(1 for s in predicted.services.values() if s.status == ServiceStatus.running)
        total = len(predicted.services) or 1
        metrics = SimMetrics(
            availability=running / total,
            avg_latency=sum(n.latency_ms for n in predicted.nodes.values()) / len(predicted.nodes),
            max_latency=max((n.latency_ms for n in predicted.nodes.values()), default=0.0),
            worst_node_load=max((n.load / n.capacity for n in predicted.nodes.values()), default=0.0),
            unreachable_services=[s.id for s in predicted.services.values() if s.status == ServiceStatus.down],
            path_count=sum(1 for s in predicted.services.values() if s.path),
        )
        return SimulationResult(
            id=new_sim_id(), plan_id=plan.id, based_on_version=state_copy.version, feasible=True,
            metrics=metrics, delta=SimDelta(availability=0.0, avg_latency=0.0, max_latency=0.0),
            computed_at=utcnow(),
        )


# --------------------------------------------------------------------------
# Hrishi: Safety Gate
# --------------------------------------------------------------------------

class FakeSafetyGate:
    def evaluate(self, before, simulation, plan, policy: PolicyConfig) -> SafetyDecision:
        violations: list[Violation] = []
        if not simulation.feasible:
            violations.append(Violation(
                rule="twin_infeasible", detail=simulation.infeasible_reason or "infeasible", level="critical"
            ))
        for action in plan.actions:
            if getattr(action, "node_id", None) in PROTECTED_NODES:
                violations.append(Violation(
                    rule="protected_infrastructure",
                    detail=f"action {action.type} targets protected node {action.node_id}", level="critical",
                ))
        approved = not any(v.level == "critical" for v in violations)
        return SafetyDecision(
            plan_id=plan.id, based_on_version=before.version, approved=approved, violations=violations,
            evaluated={"availability": simulation.metrics.availability if simulation.metrics else 0.0},
            policy_version=policy.policy_version, decided_at=utcnow(),
        )
