"""Fault contract. Source of truth: docs/BACKEND_SCHEMA.md §4.

`FaultRequest` is the REST input; `Fault` is the tracked record. How params map to
concrete field changes and how a cleared fault restores elements is Sahil's
(`backend/faults/`). Vikash's layer only validates the shape and routes it.
"""

from __future__ import annotations

from pydantic import Field

from .common import FAULT_ID, StrictModel, UtcDatetime
from .enums import FaultType


class FaultRequest(StrictModel):
    type: FaultType
    target: str = Field(min_length=1, description="node id or edge id, per fault type")
    params: dict[str, float] | None = Field(default=None, description="type-specific, optional")


class Fault(StrictModel):
    id: str = Field(pattern=FAULT_ID)
    type: FaultType
    target: str
    params: dict[str, float] = Field(default_factory=dict)
    created_at: UtcDatetime
