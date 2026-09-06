"""RecoveryAction closed vocabulary + RecoveryPlan validation."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.models.recovery import RecoveryAction, RecoveryPlan
from tests import fixtures

_action = TypeAdapter(RecoveryAction)


@pytest.mark.parametrize("raw,expected", [
    ({"type": "reroute", "service_id": "svc-a"}, "RerouteAction"),
    ({"type": "drain_node", "node_id": "N1"}, "DrainNodeAction"),
    ({"type": "restore_node", "node_id": "N1"}, "RestoreNodeAction"),
    ({"type": "migrate_service", "service_id": "svc-a", "to_node": "N2"}, "MigrateServiceAction"),
    ({"type": "quarantine_node", "node_id": "N1"}, "QuarantineNodeAction"),
    ({"type": "reset_link", "edge_id": "N1-N2"}, "ResetLinkAction"),
])
def test_each_action_type_parses(raw, expected):
    assert type(_action.validate_python(raw)).__name__ == expected


def test_out_of_vocabulary_action_rejected():
    with pytest.raises(ValidationError):
        _action.validate_python({"type": "shell", "cmd": "rm -rf /"})


def test_action_rejects_extra_field():
    with pytest.raises(ValidationError):
        _action.validate_python({"type": "quarantine_node", "node_id": "N1", "force": True})


def test_plan_action_count_bounds():
    base = fixtures.recovery_plan().model_dump()
    base["actions"] = []
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(base)
    base["actions"] = [{"type": "drain_node", "node_id": f"N{i}"} for i in range(7)]
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(base)


def test_plan_rejects_bad_id_pattern():
    base = fixtures.recovery_plan().model_dump()
    base["id"] = "plan-XYZ"
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(base)
