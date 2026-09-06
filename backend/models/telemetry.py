"""Telemetry contract — derived, read-only projection of NetworkState.

Source of truth: docs/BACKEND_SCHEMA.md §3. Output of `backend/telemetry/` (Sahil).
Never stored inside NetworkState. This module fixes the shape only; the
derivation math (including the `network_availability` formula — TEAM DECISION D1)
is Sahil's.
"""

from __future__ import annotations

from pydantic import Field

from .common import StrictModel, UtcDatetime
from .enums import NodeStatus


class NodeTelemetry(StrictModel):
    cpu_percent: float
    latency_ms: float
    packet_loss_percent: float
    status: NodeStatus


class Telemetry(StrictModel):
    at: UtcDatetime
    based_on_version: int = Field(ge=0)
    network_availability: float = Field(ge=0.0, le=1.0, description="fraction of services operational — formula owned by Sahil (D1)")
    avg_latency: float = Field(ge=0.0, description="mean end-to-end service path latency (ms)")
    max_latency: float = Field(ge=0.0, description="worst service path latency (ms)")
    total_packet_loss: float = Field(ge=0.0, le=1.0, description="aggregate packet loss ratio")
    active_nodes: int = Field(ge=0)
    failed_nodes: int = Field(ge=0)
    quarantined_nodes: int = Field(ge=0)
    congested_edges: int = Field(ge=0)
    failed_edges: int = Field(ge=0)
    per_node: dict[str, NodeTelemetry]
