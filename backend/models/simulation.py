"""SimulationResult contract — output of twin/ (owned by Sahil).

Source of truth: docs/BACKEND_SCHEMA.md §6.1. This module fixes the shape; the
simulation method and per-action state transforms are teammate-internal.
"""

from __future__ import annotations

from pydantic import Field

from .common import PLAN_ID, StrictModel, UtcDatetime


class SimMetrics(StrictModel):
    availability: float = Field(ge=0.0, le=1.0)
    avg_latency: float = Field(ge=0.0)
    max_latency: float = Field(ge=0.0)
    worst_node_load: float = Field(ge=0.0, description="max(load / capacity) across nodes")
    unreachable_services: list[str] = Field(default_factory=list)
    path_count: int = Field(ge=0)


class SimDelta(StrictModel):
    availability: float
    avg_latency: float
    max_latency: float


class SimulationResult(StrictModel):
    plan_id: str = Field(pattern=PLAN_ID)
    based_on_version: int = Field(ge=0)
    feasible: bool
    infeasible_reason: str | None = None
    metrics: SimMetrics | None = None
    delta: SimDelta | None = None
    errors: list[str] = Field(default_factory=list)
    computed_at: UtcDatetime
