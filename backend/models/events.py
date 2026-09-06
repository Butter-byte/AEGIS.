"""WebSocket event envelope — server -> frontend only.

Source of truth: docs/BACKEND_SCHEMA.md §11.

One envelope for all seven event types. `payload` stays a plain mapping so any
event shape fits without a class per type; the per-type payload contents are
documented in BACKEND_SCHEMA.md §11 and built by `backend/events/`.

The WebSocket is observation-only. Inbound frames are ignored. It is never a
mutation path.
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
    version: int | None = Field(default=None, description="NetworkState version this event relates to, or null")
    payload: dict[str, Any] = Field(default_factory=dict)
