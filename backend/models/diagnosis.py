"""Diagnosis contract — output of `backend/diagnosis/` (Yyash).

Source of truth: docs/BACKEND_SCHEMA.md §5. ADVISORY ONLY. This fixes the shape;
how suspicion / confidence / rationale are produced is Yyash's, and is later
swappable for an LLM behind the same shape.
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
    source: str = Field(default="mock", description='"mock" | "heuristic" | "llm" — provenance')
