"""Apply mechanical mutations to a NetworkState COPY without committing (Vikash).

Used where a caller must see the post-mutation state before it is committed —
the fault route and the Executor both build a structural batch, then ask the
NetworkModel to recompute status against the preview, then commit ONE batch.

This does the same field merges as `StateManager.apply_actions`, minus the
version bump / validation / commit. `StateManager` remains the only committer.
"""

from __future__ import annotations

from backend.models.state import NetworkState
from backend.state.mutations import (
    Mutation,
    SetActiveFaults,
    SetEdgeFields,
    SetNodeFields,
    SetServiceFields,
)


def preview(state: NetworkState, mutations: list[Mutation]) -> NetworkState:
    draft = state.model_dump()
    nodes = draft["nodes"]
    services = draft["services"]
    edges_by_id = {e["id"]: e for e in draft["edges"]}
    for m in mutations:
        if isinstance(m, SetNodeFields) and m.node_id in nodes:
            nodes[m.node_id].update(m.fields)
        elif isinstance(m, SetEdgeFields) and m.edge_id in edges_by_id:
            edges_by_id[m.edge_id].update(m.fields)
        elif isinstance(m, SetServiceFields) and m.service_id in services:
            services[m.service_id].update(m.fields)
        elif isinstance(m, SetActiveFaults):
            draft["active_fault_ids"] = list(m.fault_ids)
    return NetworkState.model_validate(draft)
