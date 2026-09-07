"""NetworkState / NodeState / EdgeState / ServiceState structural invariants.

Edge ids order LEXICALLY (`source < target` as strings) per BACKEND_SCHEMA.md
§1.1 and `models.common.edge_id_for`. `ServiceState.path` carries no structural
validation in the current model (flagged in the reconciliation report).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.common import edge_id_for
from backend.models.state import EdgeState, NetworkState, NodeState
from tests import fixtures


def test_edge_id_orders_lexically():
    # "N10" < "N2" as strings, so the id puts N10 first
    assert edge_id_for("N2", "N10") == "N10-N2"
    assert edge_id_for("N10", "N2") == "N10-N2"
    assert edge_id_for("N1", "N2") == "N1-N2"


@pytest.mark.parametrize("bad", [
    {"id": "X1"}, {"cpu_percent": 150.0}, {"packet_loss_percent": 101.0}, {"capacity": 0.0},
])
def test_nodestate_field_validation(bad):
    base = dict(id="N1", status="healthy", cpu_percent=10.0, latency_ms=1.0,
                packet_loss_percent=0.0, capacity=100.0, load=1.0)
    base.update(bad)
    with pytest.raises(ValidationError):
        NodeState.model_validate(base)


def test_edge_id_must_match_endpoints_in_lexical_order():
    # id "N2-N10" is wrong: lexical order is N10 then N2
    with pytest.raises(ValidationError):
        EdgeState.model_validate(dict(
            id="N2-N10", source="N2", target="N10", bandwidth_mbps=1.0, latency_ms=1.0,
            packet_loss_percent=0.0, utilization_percent=0.0, status="active",
        ))


def test_edge_rejects_equal_endpoints():
    with pytest.raises(ValidationError):
        EdgeState.model_validate(dict(
            id="N1-N1", source="N1", target="N1", bandwidth_mbps=1.0, latency_ms=1.0,
            packet_loss_percent=0.0, utilization_percent=0.0, status="active",
        ))


def test_networkstate_rejects_service_on_unknown_node():
    data = fixtures.network_state().model_dump()
    data["services"]["svc-auth"]["host_node"] = "N99"
    with pytest.raises(ValidationError):
        NetworkState.model_validate(data)


def test_networkstate_rejects_duplicate_edge_id():
    data = fixtures.network_state().model_dump()
    data["edges"].append(dict(data["edges"][0]))
    with pytest.raises(ValidationError):
        NetworkState.model_validate(data)


def test_networkstate_rejects_edge_to_unknown_node():
    data = fixtures.network_state().model_dump()
    data["edges"][0]["target"] = "N99"
    data["edges"][0]["id"] = edge_id_for(data["edges"][0]["source"], "N99")
    with pytest.raises(ValidationError):
        NetworkState.model_validate(data)


def test_networkstate_rejects_empty_nodes():
    data = fixtures.network_state().model_dump()
    data["nodes"] = {}
    with pytest.raises(ValidationError):
        NetworkState.model_validate(data)


# --- ServiceState.path — currently a free list[str] (no structural check) ---

def _with_path(path):
    data = fixtures.network_state().model_dump(mode="python")
    data["services"]["svc-auth"]["path"] = path
    return data


def test_empty_path_allowed():
    NetworkState.model_validate(_with_path([]))


def test_valid_path_roundtrips():
    s = NetworkState.model_validate(_with_path(["N2", "N1", "N3"]))
    assert s.services["svc-auth"].path == ["N2", "N1", "N3"]
