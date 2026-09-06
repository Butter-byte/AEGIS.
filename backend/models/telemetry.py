"""Telemetry contract — output of telemetry/ (owned by Sahil).

Source of truth: docs/BACKEND_SCHEMA.md §3. Derived, read-only projection of
NetworkState; never stored in NetworkState. This module fixes only the shape —
the derivation math (including the network_availability formula, TEAM DECISION)
is teammate-internal.
"""

from __future__ import annotations

from pydantic import Field

from .common import StrictModel, UtcDatetime
from .enums import NodeStatus


class NodeTelemetry(StrictModel):
    cpu: float
    latency: float
    packet_loss: float
    status: NodeStatus


class Telemetry(StrictModel):
    at: UtcDatetime
    based_on_version: int = Field(ge=0)
    network_availability: float = Field(ge=0.0, le=1.0)
    avg_latency: float = Field(ge=0.0)
    max_latency: float = Field(ge=0.0)
    total_packet_loss: float = Field(ge=0.0, le=1.0)
    active_nodes: int = Field(ge=0)
    failed_nodes: int = Field(ge=0)
    quarantined_nodes: int = Field(ge=0)
    congested_edges: int = Field(ge=0)
    failed_edges: int = Field(ge=0)
    per_node: dict[str, NodeTelemetry]
