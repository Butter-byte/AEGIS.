"""Diagnosis contract — output of ai/ (owned by Yyash).

Source of truth: docs/BACKEND_SCHEMA.md §4. Advisory only. This module fixes the
shape; how suspicion / confidence / rationale are produced is teammate-internal.
"""

from __future__ import annotations

from pydantic import Field

from .common import DIAGNOSIS_ID, StrictModel, UtcDatetime


class Diagnosis(StrictModel):
    id: str = Field(pattern=DIAGNOSIS_ID)
    created_at: UtcDatetime
    based_on_version: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=500)
    suspected_nodes: list[str] = Field(default_factory=list)
    suspected_edges: list[str] = Field(default_factory=list)
    suspected_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=2000)
