from __future__ import annotations

from collections.abc import Iterable
import random

import networkx as nx

from backend.models.common import edge_id_for, utcnow
from backend.models.enums import EdgeStatus, NodeStatus, ServiceStatus
from backend.models.recovery import (
    DrainNodeAction,
    MigrateServiceAction,
    QuarantineNodeAction,
    RecoveryAction,
    ResetLinkAction,
    RestoreNodeAction,
    RerouteAction,
)
from backend.models.state import EdgeState, NetworkState, NodeState, ServiceState
from backend.state.mutations import Mutation, set_edge, set_node


class NetworkModel:
    """NetworkModel contract used by simulation, telemetry, and recovery."""

    def resolve_path(
        self,
        state: NetworkState,
        source: str,
        target: str,
        *,
        avoid_nodes: Iterable[str] = (),
        avoid_edges: Iterable[str] = (),
    ) -> list[str] | None:
        return shortest_path(state, source, target, avoid_nodes=avoid_nodes, avoid_edges=avoid_edges)

    def recompute_status(self, state: NetworkState) -> list[Mutation]:
        mutations: list[Mutation] = []
        for node in state.nodes.values():
            expected = NodeStatus.healthy
            load_ratio = node.load / node.capacity
            if node.status in {NodeStatus.failed, NodeStatus.quarantined}:
                continue
            if node.cpu_percent >= 90.0 or load_ratio >= 0.90 or node.packet_loss_percent >= 20.0:
                expected = NodeStatus.degraded
            if node.status != expected:
                mutations.append(set_node(node.id, status=expected.value))

        for edge in state.edges:
            if edge.status == EdgeStatus.failed:
                continue
            expected = EdgeStatus.congested if edge.utilization_percent >= 90.0 or edge.packet_loss_percent >= 20.0 else EdgeStatus.active
            if edge.status != expected:
                mutations.append(set_edge(edge.id, status=expected.value))
        return mutations

_CORE_NODES = {"N1", "N5", "N10", "N15"}
_AGG_NODES = {"N2", "N4", "N6", "N8", "N11"}
_EDGE_NODES = {"N3", "N7", "N9", "N12", "N13", "N14"}


def build_seed() -> NetworkState:
    """Build the canonical 15-node seed with dynamic, heterogeneous resource allocation."""
    node_ids = [f"N{i}" for i in range(1, 16)]
    nodes: dict[str, NodeState] = {}

    for node_id in node_ids:
        if node_id in _CORE_NODES:
            # Core backbone routers: high capacity, low latency
            capacity = round(random.uniform(1800.0, 2400.0), 1)
            load = round(random.uniform(400.0, 800.0), 1)
            latency = round(random.uniform(3.5, 7.5), 1)
            cpu = round(random.uniform(25.0, 45.0), 1)
        elif node_id in _AGG_NODES:
            # Aggregation switches: medium capacity, balanced latency
            capacity = round(random.uniform(1100.0, 1600.0), 1)
            load = round(random.uniform(300.0, 600.0), 1)
            latency = round(random.uniform(7.0, 13.0), 1)
            cpu = round(random.uniform(28.0, 48.0), 1)
        else:
            # Edge compute / access nodes: standard capacity, higher latency
            capacity = round(random.uniform(750.0, 1100.0), 1)
            load = round(random.uniform(200.0, 450.0), 1)
            latency = round(random.uniform(11.0, 18.0), 1)
            cpu = round(random.uniform(20.0, 42.0), 1)

        nodes[node_id] = NodeState(
            id=node_id,
            status=NodeStatus.healthy,
            cpu_percent=cpu,
            latency_ms=latency,
            packet_loss_percent=0.0,
            capacity=capacity,
            load=load,
        )

    links = [
        (f"N{i}", f"N{i + 1}") for i in range(1, 15)
    ] + [("N1", "N5"), ("N5", "N10"), ("N10", "N15"), ("N1", "N15")]

    edges = []
    for source, target in links:
        s_min, s_max = min(source, target), max(source, target)
        is_backbone = (s_min, s_max) in {("N1", "N5"), ("N5", "N10"), ("N10", "N15"), ("N1", "N15")}
        bw = 20000.0 if is_backbone else 10000.0
        lat = round(random.uniform(2.0, 4.5), 1) if is_backbone else round(random.uniform(4.5, 8.5), 1)
        util = round(random.uniform(30.0, 55.0), 1) if is_backbone else round(random.uniform(25.0, 60.0), 1)

        edges.append(
            EdgeState(
                id=edge_id_for(source, target),
                source=s_min,
                target=s_max,
                bandwidth_mbps=bw,
                latency_ms=lat,
                packet_loss_percent=0.0,
                utilization_percent=util,
                status=EdgeStatus.active,
            )
        )

    services = {
        "svc-auth": ServiceState(
            id="svc-auth",
            host_node="N2",
            path=[],
            required_bandwidth=round(random.uniform(220.0, 280.0), 1),
            status=ServiceStatus.running,
        ),
        "svc-payment": ServiceState(
            id="svc-payment",
            host_node="N7",
            path=[],
            required_bandwidth=round(random.uniform(450.0, 550.0), 1),
            status=ServiceStatus.running,
        ),
        "svc-api": ServiceState(
            id="svc-api",
            host_node="N11",
            path=[],
            required_bandwidth=round(random.uniform(320.0, 380.0), 1),
            status=ServiceStatus.running,
        ),
    }

    state = NetworkState(
        version=0,
        updated_at=utcnow(),
        nodes=nodes,
        edges=edges,
        services=services,
        active_fault_ids=[],
    )
    model = NetworkModel()
    for service in state.services.values():
        service.path = model.resolve_path(state, "N1", service.host_node) or []
    return state


def drift_network_resources(state: NetworkState) -> list[Mutation]:
    """Generate subtle realistic perturbations simulating dynamic operational traffic.

    Safe & bounded: does not transition node health statuses; failed/quarantined nodes
    stay inactive, while healthy nodes fluctuate within realistic operating bands.
    """
    mutations: list[Mutation] = []

    for node in state.nodes.values():
        if node.status in {NodeStatus.failed, NodeStatus.quarantined}:
            continue

        # Subtle drift
        delta_cpu = round(random.uniform(-2.5, 2.5), 1)
        new_cpu = round(max(15.0, min(70.0, node.cpu_percent + delta_cpu)), 1)

        delta_lat = round(random.uniform(-0.6, 0.6), 1)
        new_lat = round(max(2.0, min(35.0, node.latency_ms + delta_lat)), 1)

        delta_load = round(random.uniform(-18.0, 18.0), 1)
        new_load = round(max(50.0, min(node.capacity * 0.85, node.load + delta_load)), 1)

        if (
            new_cpu != node.cpu_percent
            or new_lat != node.latency_ms
            or new_load != node.load
        ):
            mutations.append(set_node(node.id, cpu_percent=new_cpu, latency_ms=new_lat, load=new_load))

    for edge in state.edges:
        if edge.status == EdgeStatus.failed:
            continue

        delta_util = round(random.uniform(-2.0, 2.0), 1)
        new_util = round(max(15.0, min(80.0, edge.utilization_percent + delta_util)), 1)

        delta_lat = round(random.uniform(-0.3, 0.3), 1)
        new_lat = round(max(1.5, min(25.0, edge.latency_ms + delta_lat)), 1)

        if new_util != edge.utilization_percent or new_lat != edge.latency_ms:
            mutations.append(set_edge(edge.id, utilization_percent=new_util, latency_ms=new_lat))

    return mutations


def to_graph(state: NetworkState) -> nx.Graph:
    """Create a temporary weighted graph view from canonical network state."""
    graph = nx.Graph()
    for node in state.nodes.values():
        if node.status not in {NodeStatus.failed, NodeStatus.quarantined}:
            graph.add_node(node.id)

    for edge in state.edges:
        if edge.status == EdgeStatus.failed:
            continue
        if edge.source not in graph or edge.target not in graph:
            continue
        graph.add_edge(
            edge.source,
            edge.target,
            id=edge.id,
            weight=edge.latency_ms
            + edge.utilization_percent
            + edge.packet_loss_percent,
        )
    return graph


def shortest_path(
    state: NetworkState,
    source: str,
    target: str,
    *,
    avoid_nodes: Iterable[str] = (),
    avoid_edges: Iterable[str] = (),
) -> list[str] | None:
    """Return the lowest-cost available path without changing ``state``."""
    graph = to_graph(state)
    graph.remove_nodes_from(set(avoid_nodes))
    avoided_edges = set(avoid_edges)
    graph.remove_edges_from(
        (edge.source, edge.target)
        for edge in state.edges
        if edge.id in avoided_edges
    )
    if source not in graph or target not in graph:
        return None
    try:
        return nx.shortest_path(graph, source, target, weight="weight")
    except nx.NetworkXNoPath:
        return None


def apply_action(state: NetworkState, action: RecoveryAction) -> NetworkState:
    """Apply one validated recovery action to an isolated state copy.

    This helper does not update versions or the live StateManager. The Digital
    Twin may use it on a deep copy; Execution uses its own StateManager path.
    """
    simulated = state.model_copy(deep=True)
    incident_edges = {
        node_id: [
            edge.id
            for edge in simulated.edges
            if edge.source == node_id or edge.target == node_id
        ]
        for node_id in simulated.nodes
    }

    if isinstance(action, QuarantineNodeAction):
        simulated.nodes[action.node_id].status = NodeStatus.quarantined
        for edge in simulated.edges:
            if edge.id in incident_edges[action.node_id]:
                edge.status = EdgeStatus.failed
    elif isinstance(action, DrainNodeAction):
        simulated.nodes[action.node_id].status = NodeStatus.degraded
    elif isinstance(action, RestoreNodeAction):
        simulated.nodes[action.node_id].status = NodeStatus.healthy
        for edge in simulated.edges:
            if edge.id in incident_edges[action.node_id]:
                edge.status = EdgeStatus.active
    elif isinstance(action, ResetLinkAction):
        next(edge for edge in simulated.edges if edge.id == action.edge_id).status = EdgeStatus.active
    elif isinstance(action, MigrateServiceAction):
        simulated.services[action.service_id].host_node = action.to_node
    elif isinstance(action, RerouteAction):
        # Rerouting is represented by path selection, not a live-state mutation.
        pass

    simulated.updated_at = utcnow()
    return simulated


