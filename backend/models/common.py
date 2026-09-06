"""Shared primitives for every canonical model.

Source of truth: docs/BACKEND_SCHEMA.md §1.

`backend/models/` is a LEAF package (Vikash-owned). It imports nothing else from
`backend/`. Every cross-module value in AEGIS is one of these types.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer


class StrictModel(BaseModel):
    """All canonical models forbid unknown fields — a malformed payload with an
    extra key is rejected at the boundary, not silently accepted."""

    model_config = ConfigDict(extra="forbid")


# --- UTC timestamps -------------------------------------------------------

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


# --- Identifier patterns -------------------------------------------------

NODE_ID = r"^N\d+$"
EDGE_ID = r"^N\d+-N\d+$"
SERVICE_ID = r"^svc-[a-z0-9-]+$"
FAULT_ID = r"^flt-[0-9a-f]{8}$"
DIAGNOSIS_ID = r"^dx-[0-9a-f]{8}$"
PLAN_ID = r"^plan-[0-9a-f]{8}$"
SIM_ID = r"^sim-[0-9a-f]{8}$"
RUN_ID = r"^run-[0-9a-f]{8}$"

_NODE_NUM = re.compile(r"^N(\d+)$")


def _suffix() -> str:
    return uuid4().hex[:8]


def new_fault_id() -> str:
    return f"flt-{_suffix()}"


def new_diagnosis_id() -> str:
    return f"dx-{_suffix()}"


def new_plan_id() -> str:
    return f"plan-{_suffix()}"


def new_sim_id() -> str:
    return f"sim-{_suffix()}"


def new_run_id() -> str:
    return f"run-{_suffix()}"


def edge_id_for(a: str, b: str) -> str:
    """Canonical undirected edge id: endpoints ordered by node NUMBER.

    Numeric (not lexical) ordering so `N2`/`N10` sorts as `N2-N10`, which keeps
    the id stable for topologies larger than 9 nodes.
    """
    ma, mb = _NODE_NUM.match(a), _NODE_NUM.match(b)
    if not ma or not mb:
        raise ValueError(f"edge endpoints must match {NODE_ID!r}: {a!r}, {b!r}")
    lo, hi = sorted((a, b), key=lambda n: int(n[1:]))
    return f"{lo}-{hi}"
