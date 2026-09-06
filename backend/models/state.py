"""Canonical network state models — the single source of truth.

Source of truth: docs/BACKEND_SCHEMA.md §2.

Owned/created by StateManager; mutated only via StateManager.apply_actions().
Teammate-internal (Sahil): how these field values are *computed* from topology
and faults. This module only fixes the shapes and structural invariants.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import EDGE_ID, FAULT_ID, NODE_ID, SERVICE_ID, StrictModel, UtcDatetime, edge_id_for
from .enums import EdgeStatus, NodeStatus, ServiceStatus


class NodeState(StrictModel):
    id: str = Field(pattern=NODE_ID)
    status: NodeStatus
    cpu_percent: float = Field(ge=0.0, le=100.0, description="CPU utilization %")
    latency_ms: float = Field(ge=0.0, description="processing latency contribution (ms)")
    packet_loss_percent: float = Field(ge=0.0, le=100.0, description="local packet loss %")
    capacity: float = Field(gt=0.0, description="max traffic units the node can route")
    load: float = Field(ge=0.0, description="current traffic units routed through node")


class EdgeState(StrictModel):
    id: str = Field(pattern=EDGE_ID)
    source: str = Field(pattern=NODE_ID)
    target: str = Field(pattern=NODE_ID)
    bandwidth_mbps: float = Field(gt=0.0, description="link capacity (Mbps)")
    latency_ms: float = Field(ge=0.0, description="propagation latency (ms)")
    packet_loss_percent: float = Field(ge=0.0, le=100.0, description="link packet loss %")
    utilization_percent: float = Field(ge=0.0, le=100.0, description="fraction of bandwidth in use, expressed as %")
    status: EdgeStatus

    @model_validator(mode="after")
    def _id_matches_endpoints(self) -> "EdgeState":
        if self.source == self.target:
            raise ValueError("edge source and target must differ")
        expected = edge_id_for(self.source, self.target)
        if self.id != expected:
            raise ValueError(f"edge id {self.id!r} must equal {expected!r} (lexical order)")
        return self


class ServiceState(StrictModel):
    id: str = Field(pattern=SERVICE_ID)
    host_node: str = Field(pattern=NODE_ID)
    required_bandwidth: float = Field(ge=0.0, description="bandwidth needed on the path (Mbps)")
    status: ServiceStatus
    depends_on: list[str] = Field(default_factory=list)


class NetworkState(StrictModel):
    version: int = Field(ge=0)
    updated_at: UtcDatetime
    nodes: dict[str, NodeState]
    edges: list[EdgeState]
    services: dict[str, ServiceState]
    active_fault_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _structural_invariants(self) -> "NetworkState":
        if not self.nodes:
            raise ValueError("network must have at least one node")

        for key, node in self.nodes.items():
            if key != node.id:
                raise ValueError(f"nodes key {key!r} != node.id {node.id!r}")
        for key, svc in self.services.items():
            if key != svc.id:
                raise ValueError(f"services key {key!r} != service.id {svc.id!r}")

        node_ids = set(self.nodes)
        seen_edges: set[str] = set()
        for edge in self.edges:
            if edge.id in seen_edges:
                raise ValueError(f"duplicate edge id {edge.id!r}")
            seen_edges.add(edge.id)
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"edge {edge.id!r} references a node not in nodes")

        for svc in self.services.values():
            if svc.host_node not in node_ids:
                raise ValueError(f"service {svc.id!r} host_node {svc.host_node!r} not in nodes")

        import re

        for fid in self.active_fault_ids:
            if not re.match(FAULT_ID, fid):
                raise ValueError(f"malformed fault id {fid!r} in active_fault_ids")
        # Note: that each active_fault_id corresponds to a *tracked* fault is a
        # cross-object invariant enforced by StateManager / FaultInjector, not here.
        return self
