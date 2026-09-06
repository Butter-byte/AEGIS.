"""WebSocket event envelope.

Source of truth: docs/BACKEND_SCHEMA.md §7.

Per-type payload shapes are documented in §7. They are built by the broadcaster
via typed helpers (backend/api/ws.py); the envelope keeps `payload` as a plain
mapping so any of the seven event shapes fits without a class per type.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import StrictModel, UtcDatetime
from .enums import WSEventType


class WSEvent(StrictModel):
    type: WSEventType
    seq: int = Field(ge=0, description="per-connection monotonic counter")
    at: UtcDatetime
    version: int | None = Field(default=None, description="NetworkState version this event relates to")
    payload: dict[str, Any] = Field(default_factory=dict)
