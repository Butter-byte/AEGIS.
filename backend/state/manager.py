"""StateManager — the single runtime owner of the authoritative NetworkState.

Source of truth: docs/TRD.md §"Authoritative state".

Invariants enforced here:
  * exactly one live NetworkState (this object holds it)
  * only `apply_actions()` / `reset()` mutate it
  * callers receive deep copies from `get_state()` — never the live object
  * `version` is monotonic (+1 per committed mutation), never reset
  * a mutation is atomic: built + fully re-validated on a draft; only a valid
    result is swapped in, and only then is `version` bumped and subscribers
    notified. A failed mutation leaves the live state untouched.

No locking: single worker, mutations run on the event loop.
<!-- ponytail: single-writer relies on one uvicorn worker; add asyncio.Lock only
     if we ever run multiple workers, which the MVP will not -->
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from backend.models.common import utcnow
from backend.models.state import NetworkState
from backend.state.mutations import (
    Mutation,
    SetActiveFaults,
    SetEdgeFields,
    SetNodeFields,
    SetServiceFields,
)

Subscriber = Callable[[NetworkState], None]


class StateInvariantError(Exception):
    """A mutation would produce an invalid NetworkState; the live state is kept."""


class StateManager:
    def __init__(self, seed: NetworkState) -> None:
        self._state: NetworkState = seed.model_copy(deep=True)
        self._subscribers: list[Subscriber] = []
        self._subscriber_errors: list[Exception] = []

    # --- reads ----------------------------------------------------------

    def current_version(self) -> int:
        return self._state.version

    def get_state(self) -> NetworkState:
        """Deep copy — callers cannot mutate the live state through it."""
        return self._state.model_copy(deep=True)

    snapshot = get_state

    # --- subscriptions ------------------------------------------------

    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def _notify(self) -> None:
        snap = self._state.model_copy(deep=True)
        for cb in list(self._subscribers):
            try:
                cb(snap)
            except Exception as exc:  # noqa: BLE001 - a broken subscriber must not undo a committed mutation
                self._subscriber_errors.append(exc)

    # --- the single mutation boundary -------------------------------

    def apply_actions(self, mutations: list[Mutation], reason: str) -> NetworkState:
        if not mutations:
            raise StateInvariantError("apply_actions called with no mutations")

        draft = self._state.model_dump()
        nodes: dict = draft["nodes"]
        edges: list = draft["edges"]
        services: dict = draft["services"]
        edges_by_id = {e["id"]: e for e in edges}

        for m in mutations:
            if isinstance(m, SetNodeFields):
                if m.node_id not in nodes:
                    raise StateInvariantError(f"unknown node {m.node_id!r}")
                nodes[m.node_id].update(m.fields)
            elif isinstance(m, SetEdgeFields):
                if m.edge_id not in edges_by_id:
                    raise StateInvariantError(f"unknown edge {m.edge_id!r}")
                edges_by_id[m.edge_id].update(m.fields)
            elif isinstance(m, SetServiceFields):
                if m.service_id not in services:
                    raise StateInvariantError(f"unknown service {m.service_id!r}")
                services[m.service_id].update(m.fields)
            elif isinstance(m, SetActiveFaults):
                draft["active_fault_ids"] = list(m.fault_ids)
            else:  # pragma: no cover - discriminated union is exhaustive
                raise StateInvariantError(f"unsupported mutation {type(m).__name__}")

        draft["version"] = self._state.version + 1
        draft["updated_at"] = utcnow()

        try:
            next_state = NetworkState.model_validate(draft)
        except ValidationError as exc:
            raise StateInvariantError(f"mutation rejected ({reason}): {exc}") from exc

        self._state = next_state
        self._notify()
        return self.get_state()

    def reset(self, seed: NetworkState) -> NetworkState:
        """Rebuild from a seed. A normal mutation — version keeps climbing."""
        draft = seed.model_dump()
        draft["version"] = self._state.version + 1
        draft["updated_at"] = utcnow()
        try:
            self._state = NetworkState.model_validate(draft)
        except ValidationError as exc:
            raise StateInvariantError(f"reset rejected: {exc}") from exc
        self._notify()
        return self.get_state()
