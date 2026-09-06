"""Mechanical state-write primitives — the write contract into StateManager.

Source of truth: docs/BACKEND_SCHEMA.md §13.

`StateManager.apply_actions()` does NOT accept `RecoveryAction`s or `Fault`s. It
accepts a list of these primitives, which carry NO domain semantics — just
"merge these fields into that node/edge/service". Translating a domain operation
into primitives is the caller's job:

  * `backend/faults/` (Sahil)     — Fault + params    -> primitives
  * `backend/execution/` (Vikash) — approved plan     -> primitives

"which fields, what values" is the caller's; "apply atomically and re-validate"
is StateManager's.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from backend.models.common import EDGE_ID, NODE_ID, SERVICE_ID, StrictModel

_FieldValue = Union[float, int, str, bool, list]


class SetNodeFields(StrictModel):
    op: Literal["set_node_fields"] = "set_node_fields"
    node_id: str = Field(pattern=NODE_ID)
    fields: dict[str, _FieldValue]


class SetEdgeFields(StrictModel):
    op: Literal["set_edge_fields"] = "set_edge_fields"
    edge_id: str = Field(pattern=EDGE_ID)
    fields: dict[str, _FieldValue]


class SetServiceFields(StrictModel):
    op: Literal["set_service_fields"] = "set_service_fields"
    service_id: str = Field(pattern=SERVICE_ID)
    fields: dict[str, _FieldValue]


class SetActiveFaults(StrictModel):
    op: Literal["set_active_faults"] = "set_active_faults"
    fault_ids: list[str]


Mutation = Annotated[
    Union[SetNodeFields, SetEdgeFields, SetServiceFields, SetActiveFaults],
    Field(discriminator="op"),
]


def set_node(node_id: str, **fields: _FieldValue) -> SetNodeFields:
    return SetNodeFields(node_id=node_id, fields=fields)


def set_edge(edge_id: str, **fields: _FieldValue) -> SetEdgeFields:
    return SetEdgeFields(edge_id=edge_id, fields=fields)


def set_service(service_id: str, **fields: _FieldValue) -> SetServiceFields:
    return SetServiceFields(service_id=service_id, fields=fields)


def set_active_faults(fault_ids: list[str]) -> SetActiveFaults:
    return SetActiveFaults(fault_ids=list(fault_ids))
