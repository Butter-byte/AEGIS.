"""Schema gate for AI output (Vikash).

Source of truth: docs/TRD.md §"AI output boundary".

`parse_diagnosis` / `parse_plan` turn raw dicts (e.g. decoded LLM JSON, or a mock
planner's output) into canonical models, raising a single `SchemaError` on ANY
failure so the pipeline never sees a partially-valid structure.

`parse_plan` additionally checks the CLOSED action vocabulary's referenced ids
against the source NetworkState (existence only — feasibility is the twin's job)
and that the plan is anchored to the current state version.

This is the structural half of the core invariant: an AI proposal that is not a
well-formed plan over known ids never advances to the Digital Twin.
"""

from __future__ import annotations

from pydantic import ValidationError

from .diagnosis import Diagnosis
from .recovery import (
    DrainNodeAction,
    MigrateServiceAction,
    QuarantineNodeAction,
    RecoveryPlan,
    RerouteAction,
    ResetLinkAction,
    RestoreNodeAction,
)
from .state import NetworkState


class SchemaError(ValueError):
    """Raised when raw AI output cannot be coerced into a canonical model."""


def parse_diagnosis(raw: dict) -> Diagnosis:
    try:
        return Diagnosis.model_validate(raw)
    except ValidationError as exc:
        raise SchemaError(f"invalid Diagnosis: {exc}") from exc


def parse_plan(raw: dict, source_state: NetworkState) -> RecoveryPlan:
    try:
        plan = RecoveryPlan.model_validate(raw)
    except ValidationError as exc:
        raise SchemaError(f"invalid RecoveryPlan: {exc}") from exc

    if plan.based_on_version != source_state.version:
        raise SchemaError(
            f"plan.based_on_version {plan.based_on_version} != state version {source_state.version}"
        )

    nodes = set(source_state.nodes)
    edges = {e.id for e in source_state.edges}
    services = set(source_state.services)

    def require(ref: str, universe: set[str], kind: str, idx: int, atype: str) -> None:
        if ref not in universe:
            raise SchemaError(f"action[{idx}] {atype}: unknown {kind} {ref!r}")

    for i, action in enumerate(plan.actions):
        if isinstance(action, RerouteAction):
            require(action.service_id, services, "service", i, action.type)
            for n in action.avoid_nodes:
                require(n, nodes, "node", i, action.type)
            for e in action.avoid_edges:
                require(e, edges, "edge", i, action.type)
        elif isinstance(action, (DrainNodeAction, RestoreNodeAction, QuarantineNodeAction)):
            require(action.node_id, nodes, "node", i, action.type)
        elif isinstance(action, MigrateServiceAction):
            require(action.service_id, services, "service", i, action.type)
            require(action.to_node, nodes, "node", i, action.type)
        elif isinstance(action, ResetLinkAction):
            require(action.edge_id, edges, "edge", i, action.type)

    return plan
