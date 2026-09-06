"""Digital Twin validation contract — output of `backend/twin/` (Sahil).

Source of truth: docs/BACKEND_SCHEMA.md §7.

The twin receives a NetworkState VALUE (deep copy) + one RecoveryPlan and returns
one `SimulationResult`. It must not touch live state. This module fixes the shape;
the simulation method and per-action transforms are Sahil's.
"""

from __future__ import annotations

from pydantic import Field

from .common import PLAN_ID, SIM_ID, StrictModel, UtcDatetime


class SimMetrics(StrictModel):
    availability: float = Field(ge=0.0, le=1.0)
    avg_latency: float = Field(ge=0.0)
    max_latency: float = Field(ge=0.0)
    worst_node_load: float = Field(ge=0.0, description="max(load / capacity) across nodes")
    unreachable_services: list[str] = Field(default_factory=list)
    path_count: int = Field(ge=0, description="distinct service paths resolved")


class SimDelta(StrictModel):
    availability: float
    avg_latency: float
    max_latency: float


class SimulationResult(StrictModel):
    id: str = Field(pattern=SIM_ID)
    plan_id: str = Field(pattern=PLAN_ID)
    based_on_version: int = Field(ge=0)
    feasible: bool = Field(description="could every action be applied on the copy?")
    infeasible_reason: str | None = Field(default=None, description="set iff feasible is False")
    metrics: SimMetrics | None = Field(default=None, description="null iff feasible is False")
    delta: SimDelta | None = Field(default=None, description="post-minus-pre; null iff infeasible")
    errors: list[str] = Field(default_factory=list, description="non-fatal notes")
    computed_at: UtcDatetime
