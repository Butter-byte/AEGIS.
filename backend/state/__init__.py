"""Live-state ownership. StateManager is the ONLY writer of the live NetworkState
(architecture invariant 2). Mutations enter through `apply_actions()` only.
"""

from __future__ import annotations

from backend.state.manager import StateInvariantError, StateManager
from backend.state.mutations import (
    Mutation,
    SetActiveFaults,
    SetEdgeFields,
    SetNodeFields,
    SetServiceFields,
    set_active_faults,
    set_edge,
    set_node,
    set_service,
)
from backend.state.seed import build_seed

__all__ = [
    "StateManager",
    "StateInvariantError",
    "Mutation",
    "SetNodeFields",
    "SetEdgeFields",
    "SetServiceFields",
    "SetActiveFaults",
    "set_node",
    "set_edge",
    "set_service",
    "set_active_faults",
    "build_seed",
]
