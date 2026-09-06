"""Approved RecoveryPlan -> mechanical state mutations (Vikash).

Source of truth: docs/TRD.md §"Execution".

Intentionally MINIMAL and structural. It models only the unambiguous state
effects of each action type — node/edge status, service host, and the assigned
`path` for reroute/migrate. Latency / load / utilisation recomputation belongs to
Sahil's network model + Digital Twin; the integration layer does not invent it.

`reroute` / `migrate_service` need a concrete path. Pathfinding is Sahil's
(`backend/network/`), injected here as a `PathResolver`. For integration tests a
deterministic fake resolver is used. With no resolver available, a reroute/migrate
action fails translation and the whole plan is rejected BEFORE any mutation —
never a partial apply.
"""

from __future__ import annotations

from typing import Protocol

from backend.models.enums import EdgeStatus, NodeStatus
from backend.models.recovery import (
    DrainNodeAction,
    MigrateServiceAction,
    QuarantineNodeAction,
    RecoveryPlan,
    RerouteAction,
    ResetLinkAction,
    RestoreNodeAction,
)
from backend.models.state import NetworkState
from backend.state.mutations import Mutation, set_edge, set_node, set_service


class PathResolver(Protocol):
    """Owner: Sahil (`backend/network/`). Returns a viable ordered node path for a
    service, or None if none exists. `new_host` is set for migrate_service."""

    def resolve_path(
        self,
        service_id: str,
        state: NetworkState,
        *,
        avoid_nodes: list[str] | None = None,
        avoid_edges: list[str] | None = None,
        new_host: str | None = None,
    ) -> list[str] | None: ...


class TranslationError(Exception):
    """A plan action cannot be turned into concrete mutations — abort, no partial apply."""


def plan_to_mutations(
    plan: RecoveryPlan,
    state: NetworkState,
    path_resolver: PathResolver | None = None,
) -> list[Mutation]:
    muts: list[Mutation] = []
    incident = _incident_edges(state)

    for i, action in enumerate(plan.actions):
        if isinstance(action, QuarantineNodeAction):
            muts.append(set_node(action.node_id, status=NodeStatus.quarantined.value))
            for edge_id in incident.get(action.node_id, ()):
                muts.append(set_edge(edge_id, status=EdgeStatus.failed.value))
        elif isinstance(action, DrainNodeAction):
            muts.append(set_node(action.node_id, status=NodeStatus.degraded.value))
        elif isinstance(action, RestoreNodeAction):
            muts.append(set_node(action.node_id, status=NodeStatus.healthy.value))
            for edge_id in incident.get(action.node_id, ()):
                muts.append(set_edge(edge_id, status=EdgeStatus.active.value))
        elif isinstance(action, ResetLinkAction):
            muts.append(set_edge(action.edge_id, status=EdgeStatus.active.value))
        elif isinstance(action, MigrateServiceAction):
            path = _require_path(
                path_resolver, action.service_id, state, i, new_host=action.to_node
            )
            muts.append(set_service(action.service_id, host_node=action.to_node, path=path))
        elif isinstance(action, RerouteAction):
            path = _require_path(
                path_resolver, action.service_id, state, i,
                avoid_nodes=action.avoid_nodes, avoid_edges=action.avoid_edges,
            )
            muts.append(set_service(action.service_id, path=path))

    return muts


def _require_path(
    resolver: PathResolver | None,
    service_id: str,
    state: NetworkState,
    idx: int,
    *,
    avoid_nodes: list[str] | None = None,
    avoid_edges: list[str] | None = None,
    new_host: str | None = None,
) -> list[str]:
    if resolver is None:
        raise TranslationError(
            f"action[{idx}]: reroute/migrate needs a PathResolver (backend/network/ not wired)"
        )
    path = resolver.resolve_path(
        service_id, state, avoid_nodes=avoid_nodes, avoid_edges=avoid_edges, new_host=new_host
    )
    if not path:
        raise TranslationError(f"action[{idx}]: no viable path for service {service_id!r}")
    return path


def _incident_edges(state: NetworkState) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for edge in state.edges:
        out.setdefault(edge.source, []).append(edge.id)
        out.setdefault(edge.target, []).append(edge.id)
    return out
