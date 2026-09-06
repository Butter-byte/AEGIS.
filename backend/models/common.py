"""Shared primitives for the canonical models: strict base, UTC datetime, id patterns.

Source of truth: docs/BACKEND_SCHEMA.md §1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer


class StrictModel(BaseModel):
    """All canonical models forbid unknown fields (BACKEND_SCHEMA.md §1)."""

    model_config = ConfigDict(extra="forbid")


# --- UTC timestamps (BACKEND_SCHEMA.md §1) ---------------------------------

def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (UTC)")
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[
    datetime,
    AfterValidator(_to_utc),
    PlainSerializer(_iso_z, return_type=str, when_used="json"),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Identifier patterns (BACKEND_SCHEMA.md §1.1) -------------------------

NODE_ID = r"^N\d+$"
EDGE_ID = r"^N\d+-N\d+$"
SERVICE_ID = r"^svc-[a-z0-9-]+$"
FAULT_ID = r"^flt-[0-9a-f]{8}$"
DIAGNOSIS_ID = r"^dx-[0-9a-f]{8}$"
PLAN_ID = r"^plan-[0-9a-f]{8}$"
RUN_ID = r"^run-[0-9a-f]{8}$"


def _suffix() -> str:
    return uuid4().hex[:8]


def new_fault_id() -> str:
    return f"flt-{_suffix()}"


def new_diagnosis_id() -> str:
    return f"dx-{_suffix()}"


def new_plan_id() -> str:
    return f"plan-{_suffix()}"


def new_run_id() -> str:
    return f"run-{_suffix()}"


def edge_id_for(a: str, b: str) -> str:
    """Canonical edge id: endpoints in lexical order (BACKEND_SCHEMA.md §1.1)."""
    lo, hi = sorted((a, b))
    return f"{lo}-{hi}"
