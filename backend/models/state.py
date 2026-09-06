"""Authoritative network-state contract — the single source of truth.

Source of truth: docs/BACKEND_SCHEMA.md §2.

`NetworkState` is owned at runtime by `backend/state/StateManager` and mutated
ONLY through `StateManager.apply_actions()`. Every consumer gets a deep copy.

This module fixes the SHAPES and STRUCTURAL invariants only. How the field values
are computed from a topology + faults is Sahil's; the status-vs-assigned-path
RULE (below, on `ServiceState.path`) is contract because the whole recovery story
depends on it.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import (
    EDGE_ID,
    FAULT_ID,
    NODE_ID,
    SERVICE_ID,
    StrictModel,
    UtcDatetime,
    edge_id_for,
)
from .enums import EdgeStatus, NodeStatus, ServiceStatus


class NodeState(StrictModel):
    id: str = Field(pattern=NODE_ID)
    status: NodeStatus
    cpu_percent: float = Field(ge=0.0, le=100.0, description="CPU utilisation, percentage points")
    latency_ms: float = Field(ge=0.0, description="processing latency contribution (ms)")
    packet_loss_percent: float = Field(ge=0.0, le=100.0, description="local packet loss, percentage points")
    capacity: float = Field(gt=0.0, description="max traffic units the node can route")
    load: float = Field(ge=0.0, description="current traffic units routed through the node")


class EdgeState(StrictModel):
    id: str = Field(pattern=EDGE_ID)
    source: str = Field(pattern=NODE_ID)
    target: str = Field(pattern=NODE_ID)
    bandwidth_mbps: float = Field(gt=0.0, description="link capacity (Mbps)")
    latency_ms: float = Field(ge=0.0, description="propagation latency (ms)")
    packet_loss_percent: float = Field(ge=0.0, le=100.0, description="link packet loss, percentage points")
    utilization_percent: float = Field(ge=0.0, le=100.0, description="bandwidth in use, percentage points")
    status: EdgeStatus

    @model_validator(mode="after")
    def _id_matches_endpoints(self) -> "EdgeState":
        if self.source == self.target:
            raise ValueError("edge source and target must differ")
        expected = edge_id_for(self.source, self.target)
        if self.id != expected:
            raise ValueError(f"edge id {self.id!r} must equal {expected!r} (endpoints ordered by node number)")
        return self


class ServiceState(StrictModel):
    id: str = Field(pattern=SERVICE_ID)
    host_node: str = Field(pattern=NODE_ID)
    required_bandwidth: float = Field(ge=0.0, description="bandwidth the service needs on its path (Mbps)")
    status: ServiceStatus
    depends_on: list[str] = Field(default_factory=list, description="upstream service ids")
    path: list[str] = Field(
        default_factory=list,
        description=(
            "the ASSIGNED ordered node route this service's traffic currently uses "
            "(path[0] == host_node when non-empty). CONTRACT RULE: service status is "
            "evaluated against THIS path — not against whether some alternate path "
            "exists. The path is reassigned ONLY by an executed `reroute` or "
            "`migrate_service` action. Recomputing status never changes the path. "
            "So a fault on the assigned path degrades/downs the service and it stays "
            "that way until a safety-approved recovery reroutes it."
        ),
    )


class NetworkState(StrictModel):
    version: int = Field(ge=0, description="monotonic; +1 per committed mutation; never reset")
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
        seen: set[str] = set()
        for edge in self.edges:
            if edge.id in seen:
                raise ValueError(f"duplicate edge id {edge.id!r}")
            seen.add(edge.id)
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"edge {edge.id!r} references a node not in nodes")

        edge_pairs = {frozenset((e.source, e.target)) for e in self.edges}
        for svc in self.services.values():
            if svc.host_node not in node_ids:
                raise ValueError(f"service {svc.id!r} host_node {svc.host_node!r} not in nodes")
            for dep in svc.depends_on:
                if dep not in self.services:
                    raise ValueError(f"service {svc.id!r} depends_on unknown service {dep!r}")
            if svc.path:
                if svc.path[0] != svc.host_node:
                    raise ValueError(f"service {svc.id!r} path[0] {svc.path[0]!r} != host_node {svc.host_node!r}")
                for hop in svc.path:
                    if hop not in node_ids:
                        raise ValueError(f"service {svc.id!r} path references unknown node {hop!r}")
                for a, b in zip(svc.path, svc.path[1:]):
                    if frozenset((a, b)) not in edge_pairs:
                        raise ValueError(f"service {svc.id!r} path hop {a!r}->{b!r} has no edge")

        import re

        for fid in self.active_fault_ids:
            if not re.match(FAULT_ID, fid):
                raise ValueError(f"malformed fault id {fid!r} in active_fault_ids")
        return self
