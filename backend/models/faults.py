"""Fault contract. Source of truth: docs/BACKEND_SCHEMA.md §7 (Fault) and §8
(FaultRequest).

The shape is a shared contract. FaultInjector behaviour — validating a request
against state, mapping params to concrete field changes, restoring on clear — is
teammate-internal (Sahil).
"""

from __future__ import annotations

from pydantic import Field

from .common import FAULT_ID, StrictModel, UtcDatetime
from .enums import FaultType


class FaultRequest(StrictModel):
    type: FaultType
    target: str = Field(description="node id or edge id, per fault type")
    params: dict[str, float] | None = None


class Fault(StrictModel):
    id: str = Field(pattern=FAULT_ID)
    type: FaultType
    target: str
    params: dict[str, float] = Field(default_factory=dict)
    created_at: UtcDatetime
