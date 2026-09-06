"""TEMPORARY integration scaffolding — a minimal valid seed NetworkState.

>>> This is a placeholder so AEGIS can boot with a canonical NetworkState. <<<

Sahil owns the real network. The long-term flow is:

    backend/network/  (Sahil)  ->  build_seed() -> NetworkState  ->  StateManager

When `backend/network/build_seed()` exists and returns a canonical NetworkState,
delete this file and import from there instead (one line in backend/main.py and
backend/api/routes.py). Nothing else depends on the topology here.

Kept deliberately tiny (5 nodes, 5 edges, 3 services). Not a network model —
just enough structure to exercise the state / pipeline / API / WS plumbing.
"""

from __future__ import annotations

from backend.models.common import edge_id_for, utcnow
from backend.models.enums import EdgeStatus, NodeStatus, ServiceStatus
from backend.models.state import EdgeState, NetworkState, NodeState, ServiceState

_NODES = ["N1", "N2", "N3", "N4", "N5"]
_LINKS = [("N1", "N2"), ("N1", "N3"), ("N2", "N4"), ("N3", "N4"), ("N4", "N5")]
_SERVICES = [
    ("svc-auth", "N2", 100.0),
    ("svc-api", "N4", 200.0),
    ("svc-db", "N5", 150.0),
]


def build_seed() -> NetworkState:
    nodes = {
        nid: NodeState(
            id=nid,
            status=NodeStatus.healthy,
            cpu_percent=20.0,
            latency_ms=5.0,
            packet_loss_percent=0.0,
            capacity=1000.0,
            load=100.0,
        )
        for nid in _NODES
    }
    edges = [
        EdgeState(
            id=edge_id_for(a, b),
            source=min(a, b),
            target=max(a, b),
            bandwidth_mbps=1000.0,
            latency_ms=5.0,
            packet_loss_percent=0.0,
            utilization_percent=10.0,
            status=EdgeStatus.active,
        )
        for a, b in _LINKS
    ]
    services = {
        sid: ServiceState(
            id=sid,
            host_node=host,
            required_bandwidth=bw,
            status=ServiceStatus.running,
        )
        for sid, host, bw in _SERVICES
    }
    return NetworkState(
        version=0,
        updated_at=utcnow(),
        nodes=nodes,
        edges=edges,
        services=services,
        active_fault_ids=[],
    )
