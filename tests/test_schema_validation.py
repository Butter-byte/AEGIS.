"""parse_diagnosis / parse_plan — the AI-output schema gate.

This is the structural half of "no AI output touches the network directly":
anything that is not a well-formed plan over known ids is rejected here, before
the twin.
"""

from __future__ import annotations

import pytest

from backend.models.validation import SchemaError, parse_diagnosis, parse_plan
from tests import fixtures


def test_parse_diagnosis_accepts_valid():
    assert parse_diagnosis(fixtures.diagnosis().model_dump(mode="json")).id == fixtures.DX_ID


def test_parse_diagnosis_rejects_malformed():
    with pytest.raises(SchemaError):
        parse_diagnosis({"summary": "oops"})


def test_parse_plan_accepts_valid_against_state():
    state = fixtures.network_state()
    raw = fixtures.recovery_plan(based_on_version=state.version).model_dump(mode="json")
    assert parse_plan(raw, state).id == fixtures.PLAN_ID


def test_parse_plan_rejects_unknown_referenced_node():
    state = fixtures.network_state()
    raw = fixtures.recovery_plan(based_on_version=state.version).model_dump(mode="json")
    raw["actions"] = [{"type": "quarantine_node", "node_id": "N404"}]
    with pytest.raises(SchemaError):
        parse_plan(raw, state)


def test_parse_plan_rejects_version_mismatch():
    state = fixtures.network_state()
    raw = fixtures.recovery_plan(based_on_version=999).model_dump(mode="json")
    with pytest.raises(SchemaError):
        parse_plan(raw, state)


def test_parse_plan_rejects_out_of_vocabulary_action():
    state = fixtures.network_state()
    raw = fixtures.recovery_plan(based_on_version=state.version).model_dump(mode="json")
    raw["actions"] = [{"type": "run_script", "path": "/x"}]
    with pytest.raises(SchemaError):
        parse_plan(raw, state)
