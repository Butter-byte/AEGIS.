"""Every canonical model: valid instance round-trips through JSON; extras rejected."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import NetworkState, RecoveryPlan
from tests import fixtures


@pytest.mark.parametrize("factory", fixtures.ALL_FACTORIES, ids=lambda f: f.__name__)
def test_fixture_is_valid_and_roundtrips(factory):
    obj = factory()
    dumped = obj.model_dump(mode="json")
    restored = type(obj).model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped


def test_utc_datetime_serialises_with_z():
    assert fixtures.diagnosis().model_dump(mode="json")["created_at"].endswith("Z")


def test_naive_timestamp_rejected():
    from datetime import datetime

    data = fixtures.diagnosis().model_dump(mode="python")
    data["created_at"] = datetime(2026, 1, 1)  # noqa: DTZ001 - deliberately naive
    with pytest.raises(ValidationError):
        type(fixtures.diagnosis()).model_validate(data)


def test_extra_field_rejected_everywhere():
    data = fixtures.recovery_plan().model_dump()
    data["rogue"] = 1
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(data)

    data = fixtures.network_state().model_dump()
    data["rogue"] = 1
    with pytest.raises(ValidationError):
        NetworkState.model_validate(data)
