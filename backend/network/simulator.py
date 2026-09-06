from __future__ import annotations

from collections.abc import Iterable

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


def build_seed() -> NetworkState:
    """Build the canonical 15-node seed used by StateManager."""
    node_ids = [f"N{i}" for i in range(1, 16)]
    nodes = {
        node_id: NodeState(
            id=node_id,
            status=NodeStatus.healthy,
            cpu_percent=35.0,
            latency_ms=12.0,
            packet_loss_percent=0.0,
            capacity=1000.0,
            load=450.0,
        )
        for node_id in node_ids
    }

    links = [
        (f"N{i}", f"N{i + 1}") for i in range(1, 15)
    ] + [("N1", "N5"), ("N5", "N10"), ("N10", "N15"), ("N1", "N15")]
    edges = [
        EdgeState(
            id=edge_id_for(source, target),
            source=min(source, target),
            target=max(source, target),
            bandwidth_mbps=10000.0,
            latency_ms=5.0,
            packet_loss_percent=0.0,
            utilization_percent=45.0,
            status=EdgeStatus.active,
        )
        for source, target in links
    ]

    services = {
        "svc-auth": ServiceState(
            id="svc-auth",
            host_node="N2",
            required_bandwidth=250.0,
            status=ServiceStatus.running,
        ),
        "svc-payment": ServiceState(
            id="svc-payment",
            host_node="N7",
            required_bandwidth=500.0,
            status=ServiceStatus.running,
        ),
        "svc-api": ServiceState(
            id="svc-api",
            host_node="N11",
            required_bandwidth=350.0,
            status=ServiceStatus.running,
        ),
    }

    return NetworkState(
        version=0,
        updated_at=utcnow(),
        nodes=nodes,
        edges=edges,
        services=services,
        active_fault_ids=[],
    )


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