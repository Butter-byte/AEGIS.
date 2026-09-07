"""RecoveryPlan -> state mutation primitives.

PROVISIONAL. Only the unambiguous *structural* effects (node/edge status,
service host) are modelled here. Load / latency / path / utilization effects are
part of the shared recovery-action semantics that the Digital Twin (Sahil) and
this translator MUST agree on before the demo — see INFORM Sahil in the Phase
0/1 report and TEAM DECISION D4.

`reroute` has no stored-state effect in this model (a path is computed, not
persisted), so it currently produces no mutations.
"""

from __future__ import annotations

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


def plan_to_mutations(plan: RecoveryPlan, state: NetworkState) -> list[Mutation]:
    muts: list[Mutation] = []
    incident = _incident_edges(state)

    for action in plan.actions:
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
            muts.append(
                set_edge(
                    action.edge_id,
                    status=EdgeStatus.active.value,
                    packet_loss_percent=0.08,
                    latency_ms=4.0,
                    utilization_percent=35.0,
                )
            )
        elif isinstance(action, MigrateServiceAction):
            muts.append(set_service(action.service_id, host_node=action.to_node))
        elif isinstance(action, RerouteAction):
            from backend.network.simulator import shortest_path
            svc = state.services.get(action.service_id)
            if svc:
                new_path = shortest_path(
                    state,
                    "N1",
                    svc.host_node,
                    avoid_edges=action.avoid_edges,
                    avoid_nodes=action.avoid_nodes,
                )
                if new_path:
                    muts.append(set_service(action.service_id, path=new_path))

    return muts


def _incident_edges(state: NetworkState) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for edge in state.edges:
        out.setdefault(edge.source, []).append(edge.id)
        out.setdefault(edge.target, []).append(edge.id)
    return out
