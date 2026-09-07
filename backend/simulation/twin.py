from __future__ import annotations

import networkx as nx

from backend.models.common import utcnow
from backend.models.enums import EdgeStatus, NodeStatus
from backend.models.recovery import RecoveryPlan
from backend.models.simulation import SimDelta, SimMetrics, SimulationResult
from backend.models.state import NetworkState
from backend.network.simulator import apply_action, to_graph


class DigitalTwin:
    """Deterministic, isolated simulator for a typed recovery plan."""

    def simulate(self, state: NetworkState, plan: RecoveryPlan) -> SimulationResult:
        before = self._metrics(state)
        simulated = state.model_copy(deep=True)
        try:
            for action in plan.actions:
                simulated = apply_action(simulated, action)
            after = self._metrics(simulated)
            return SimulationResult(
                plan_id=plan.id,
                based_on_version=state.version,
                feasible=not after.unreachable_services,
                infeasible_reason="one or more services would be unreachable" if after.unreachable_services else None,
                metrics=after,
                delta=SimDelta(
                    availability=after.availability - before.availability,
                    avg_latency=after.avg_latency - before.avg_latency,
                    max_latency=after.max_latency - before.max_latency,
                ),
                computed_at=utcnow(),
            )
        except Exception as exc:
            return SimulationResult(plan_id=plan.id, based_on_version=state.version, feasible=False, infeasible_reason=str(exc), errors=[str(exc)], computed_at=utcnow())

    def _metrics(self, state: NetworkState) -> SimMetrics:
        graph = to_graph(state)
        active = [node for node in state.nodes.values() if node.status not in {NodeStatus.failed, NodeStatus.quarantined}]
        active_edges = [edge for edge in state.edges if edge.status != EdgeStatus.failed]
        latencies = [node.latency_ms for node in active] + [edge.latency_ms for edge in active_edges]

        unreachable: list[str] = []
        for service in state.services.values():
            if service.host_node not in graph:
                unreachable.append(service.id)
            elif "N1" in graph and not nx.has_path(graph, "N1", service.host_node):
                unreachable.append(service.id)
            elif service.path and len(service.path) > 1:
                # If assigned route has a severed edge, service is unreachable until rerouted or link reset
                if any(not graph.has_edge(u, v) for u, v in zip(service.path, service.path[1:])):
                    unreachable.append(service.id)

        path_count = sum(1 for source in graph for target in graph if source < target and nx.has_path(graph, source, target))
        service_count = max(len(state.services), 1)
        availability = (service_count - len(unreachable)) / service_count
        return SimMetrics(
            availability=availability,
            avg_latency=sum(latencies) / max(len(latencies), 1),
            max_latency=max(latencies, default=0.0),
            worst_node_load=max((node.load / node.capacity for node in active), default=0.0),
            unreachable_services=unreachable,
            path_count=path_count,
        )