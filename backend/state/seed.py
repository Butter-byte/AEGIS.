"""TEMPORARY integration scaffold — a minimal valid seed NetworkState.

>>> NOT the real topology. Sahil owns `backend/network/build_seed()`. <<<

This exists only so Vikash's integration layer (StateManager, API, WS, pipeline)
can boot and be tested before `backend/network/` lands. The composition root
(`backend/api/context.py`) takes a `seed_source`; once Sahil's `SeedSource`
exists, `backend/main.py` injects it and this file is deleted.

6 nodes, 6 edges, 2 services with assigned paths. Deliberately small — just
enough structure to exercise every contract and every pipeline branch, including
"an alternate physical path must not auto-heal a service" (svc-auth's assigned
path N2->N1->N3 can break while N2->N4->N3 still exists).

Topology is kept identical to `tests/fixtures.network_state()`.
"""

from __future__ import annotations

from backend.models.common import edge_id_for, utcnow
from backend.models.enums import EdgeStatus, NodeStatus, ServiceStatus
from backend.models.state import EdgeState, NetworkState, NodeState, ServiceState

_NODES = ["N1", "N2", "N3", "N4", "N5", "N6"]
_LINKS = [("N1", "N2"), ("N1", "N3"), ("N2", "N4"), ("N3", "N4"), ("N4", "N5"), ("N5", "N6")]
_SERVICES = [
    ("svc-auth", "N2", 100.0, ["N2", "N1", "N3"]),
    ("svc-api", "N4", 200.0, ["N4", "N5", "N6"]),
]


def build_seed() -> NetworkState:
    nodes = {
        nid: NodeState(
            id=nid, status=NodeStatus.healthy, cpu_percent=20.0, latency_ms=5.0,
            packet_loss_percent=0.0, capacity=1000.0, load=100.0,
        )
        for nid in _NODES
    }
    edges = []
    for a, b in _LINKS:
        lo, hi = sorted((a, b), key=lambda n: int(n[1:]))
        edges.append(EdgeState(
            id=edge_id_for(a, b), source=lo, target=hi,
            bandwidth_mbps=1000.0, latency_ms=5.0, packet_loss_percent=0.0,
            utilization_percent=10.0, status=EdgeStatus.active,
        ))
    services = {
        sid: ServiceState(
            id=sid, host_node=host, required_bandwidth=bw,
            status=ServiceStatus.running, path=path,
        )
        for sid, host, bw, path in _SERVICES
    }
    return NetworkState(
        version=0, updated_at=utcnow(), nodes=nodes, edges=edges,
        services=services, active_fault_ids=[],
    )


class ScaffoldSeedSource:
    """Fills the `SeedSource` port with the scaffold seed above."""

    def build_seed(self) -> NetworkState:
        return build_seed()
