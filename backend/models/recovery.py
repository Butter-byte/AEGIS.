"""Recovery action vocabulary + RecoveryPlan — the CLOSED AI-output contract.

Source of truth: docs/BACKEND_SCHEMA.md §6.

The action vocabulary is CLOSED. A planner (mock or LLM) may emit only these six
action types. No free-form strings, shell commands, device configs, code, or SQL.
Every action forbids unknown fields. This is the structural half of the
"no AI output touches the network directly" invariant — the schema gate
(`validation.parse_plan`) rejects anything else before it ever reaches the twin.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from .common import (
    DIAGNOSIS_ID,
    EDGE_ID,
    NODE_ID,
    PLAN_ID,
    SERVICE_ID,
    StrictModel,
    UtcDatetime,
)


class RerouteAction(StrictModel):
    type: Literal["reroute"] = "reroute"
    service_id: str = Field(pattern=SERVICE_ID)
    avoid_nodes: list[str] = Field(default_factory=list)
    avoid_edges: list[str] = Field(default_factory=list)


class DrainNodeAction(StrictModel):
    type: Literal["drain_node"] = "drain_node"
    node_id: str = Field(pattern=NODE_ID)


class RestoreNodeAction(StrictModel):
    type: Literal["restore_node"] = "restore_node"
    node_id: str = Field(pattern=NODE_ID)


class MigrateServiceAction(StrictModel):
    type: Literal["migrate_service"] = "migrate_service"
    service_id: str = Field(pattern=SERVICE_ID)
    to_node: str = Field(pattern=NODE_ID)


class QuarantineNodeAction(StrictModel):
    type: Literal["quarantine_node"] = "quarantine_node"
    node_id: str = Field(pattern=NODE_ID)


class ResetLinkAction(StrictModel):
    type: Literal["reset_link"] = "reset_link"
    edge_id: str = Field(pattern=EDGE_ID)


RecoveryAction = Annotated[
    Union[
        RerouteAction,
        DrainNodeAction,
        RestoreNodeAction,
        MigrateServiceAction,
        QuarantineNodeAction,
        ResetLinkAction,
    ],
    Field(discriminator="type"),
]


class RecoveryPlan(StrictModel):
    id: str = Field(pattern=PLAN_ID)
    created_at: UtcDatetime
    based_on_version: int = Field(ge=0, description="must equal the source snapshot version")
    targets_diagnosis: str = Field(pattern=DIAGNOSIS_ID)
    strategy_label: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=2000)
    actions: list[RecoveryAction] = Field(min_length=1, max_length=6, description="ordered; order is significant")
    source: Literal["mock", "heuristic", "llm"] = "mock"
