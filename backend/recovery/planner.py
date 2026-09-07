"""Deterministic recovery planner — output of backend/recovery/ (Yyash).

Turns one canonical `Diagnosis` into 0..N candidate `RecoveryPlan`s. Every action
is one of the SIX canonical `RecoveryAction` types (closed vocabulary, invariant
4/13); no free-form operations, no custom plan model. Advisory / data-only — this
module imports nothing from `backend.state`, `backend.execution`, `backend.api`,
or `backend.pipeline` and mutates nothing. The pipeline simulates every candidate
in the Digital Twin and the Safety Engine approves before the Executor applies.

Intent is re-derived from the live status of each suspected node/edge (the
`Diagnosis` carries no `root_cause` field this phase).

`reroute` has no persisted-state effect yet (translate.py, TEAM DECISION D4), so
every emitted plan also contains at least one *effective* action
(`quarantine_node` / `migrate_service` / `restore_node` / `reset_link`). A
`reroute` action only ever rides alongside an effective one, so no plan is a
no-op — and each plan gains real reroute behaviour for free once D4 lands.
"""

from __future__ import annotations

from backend.models.common import new_plan_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import EdgeStatus, NodeStatus
from backend.models.recovery import RecoveryPlan
from backend.models.state import NetworkState

_DOWN_NODE = {NodeStatus.failed, NodeStatus.quarantined}
_MAX_ACTIONS = 6


class RecoveryPlanner:
    """Rule-based planner wired as the pipeline's `planner` port."""

    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        plans: list[RecoveryPlan] = []
        for node_id in diagnosis.suspected_nodes:
            node = state.nodes.get(node_id)
            if node is None:
                continue
            if node.status in _DOWN_NODE:
                plans += self._for_down_node(state, diagnosis, node_id)
            elif node.status == NodeStatus.degraded:
                plans += self._for_overloaded_node(state, diagnosis, node_id)

        for edge_id in diagnosis.suspected_edges:
            edge = next((e for e in state.edges if e.id == edge_id), None)
            if edge is None:
                continue
            if edge.status in {EdgeStatus.failed, EdgeStatus.congested}:
                plans += self._for_bad_edge(state, diagnosis, edge_id, edge.status)

        return plans

    # --- node strategies ----------------------------------------------------

    def _for_down_node(self, state, dx, node_id) -> list[RecoveryPlan]:
        migrations = self._migrations_off(state, node_id)
        return [self._mk(
            state, dx, f"isolate {node_id} and relocate its services",
            f"{node_id} is unreachable: move its hosted services to a healthy node, "
            f"then quarantine {node_id} so no traffic is routed through it.",
            migrations + [{"type": "quarantine_node", "node_id": node_id}],
        )]

    def _for_overloaded_node(self, state, dx, node_id) -> list[RecoveryPlan]:
        migrations = self._migrations_off(state, node_id)
        if migrations:
            return [
                self._mk(
                    state, dx, f"shed load from {node_id} by migration",
                    f"{node_id} is overloaded: relocate its hosted services to a "
                    f"healthy node to cut its CPU / forwarding load.",
                    migrations,
                ),
                self._mk(
                    state, dx, f"isolate {node_id} and relocate its services",
                    f"Firmer option: relocate {node_id}'s services and quarantine it "
                    f"so no traffic transits an overloaded node.",
                    migrations + [{"type": "quarantine_node", "node_id": node_id}],
                ),
            ]
        return [
            self._mk(
                state, dx, f"restore {node_id}",
                f"No service is hosted on {node_id}; clear its degraded state. The "
                f"Safety Engine rejects this if its load is still critical.",
                [{"type": "restore_node", "node_id": node_id}],
            ),
            self._mk(
                state, dx, f"quarantine overloaded {node_id}",
                f"Firmer option: quarantine {node_id} to force transiting traffic onto "
                f"an alternate path.",
                [{"type": "quarantine_node", "node_id": node_id}],
            ),
        ]

    # --- edge strategy ---------------------------------------------------

    def _for_bad_edge(self, state, dx, edge_id, status) -> list[RecoveryPlan]:
        word = "failed" if status == EdgeStatus.failed else "congested"
        reroutes = self._reroutes_avoiding(state, edges={edge_id})
        actions = reroutes + [{"type": "reset_link", "edge_id": edge_id}]
        label = (
            f"reroute services off {edge_id} and reset it" if reroutes
            else f"reset {word} link {edge_id}"
        )
        return [self._mk(
            state, dx, label,
            f"{edge_id} is {word}: "
            + (f"steer its {len(reroutes)} transiting service(s) onto an alternate "
               f"path and " if reroutes else "")
            + "bring the link back to active.",
            actions,
        )]

    # --- building blocks -------------------------------------------------

    @staticmethod
    def _healthy_target(state: NetworkState, exclude: set[str]) -> str | None:
        return next(
            (n.id for n in state.nodes.values()
             if n.status == NodeStatus.healthy and n.id not in exclude),
            None,
        )

    def _migrations_off(self, state: NetworkState, node_id: str) -> list[dict]:
        target = self._healthy_target(state, {node_id})
        if target is None:
            return []
        return [
            {"type": "migrate_service", "service_id": svc.id, "to_node": target}
            for svc in state.services.values()
            if svc.host_node == node_id
        ]

    @staticmethod
    def _reroutes_avoiding(state: NetworkState, *, edges: set[str]) -> list[dict]:
        out: list[dict] = []
        for svc in state.services.values():
            path_edges = {_edge_id(a, b) for a, b in zip(svc.path, svc.path[1:])}
            hit = edges & path_edges
            if hit:
                out.append({
                    "type": "reroute", "service_id": svc.id, "avoid_edges": sorted(hit),
                })
        return out

    @staticmethod
    def _mk(state, dx, label: str, rationale: str, actions: list[dict]) -> RecoveryPlan:
        # keep at least one effective (non-reroute) action if trimming is needed
        trimmed = actions[:_MAX_ACTIONS]
        if not any(a["type"] != "reroute" for a in trimmed):
            trimmed = trimmed[:-1] + [actions[-1]]
        return RecoveryPlan(
            id=new_plan_id(),
            created_at=utcnow(),
            based_on_version=state.version,
            targets_diagnosis=dx.id,
            strategy_label=label[:120],
            rationale=rationale[:2000],
            actions=trimmed,
            source="heuristic",
        )


def _edge_id(a: str, b: str) -> str:
    lo, hi = sorted((a, b))
    return f"{lo}-{hi}"
