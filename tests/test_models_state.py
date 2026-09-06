"""NetworkState / NodeState / EdgeState / ServiceState structural invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.common import edge_id_for
from backend.models.state import EdgeState, NetworkState, NodeState
from tests import fixtures


def test_edge_id_orders_by_node_number_not_lexically():
    assert edge_id_for("N2", "N10") == "N2-N10"
    assert edge_id_for("N10", "N2") == "N2-N10"


@pytest.mark.parametrize("bad", [
    {"id": "X1"}, {"cpu_percent": 150.0}, {"packet_loss_percent": 101.0}, {"capacity": 0.0},
])
def test_nodestate_field_validation(bad):
    base = dict(id="N1", status="healthy", cpu_percent=10.0, latency_ms=1.0,
                packet_loss_percent=0.0, capacity=100.0, load=1.0)
    base.update(bad)
    with pytest.raises(ValidationError):
        NodeState.model_validate(base)


def test_edge_id_must_match_endpoint_numeric_order():
    with pytest.raises(ValidationError):
        EdgeState.model_validate(dict(
            id="N10-N2", source="N10", target="N2", bandwidth_mbps=1.0, latency_ms=1.0,
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


# --- ServiceState.path — the status-vs-assigned-path contract ---

def _with_path(path):
    data = fixtures.network_state().model_dump(mode="python")
    data["services"]["svc-auth"]["path"] = path
    return data


def test_empty_path_allowed():
    NetworkState.model_validate(_with_path([]))


def test_valid_path_roundtrips():
    s = NetworkState.model_validate(_with_path(["N2", "N1", "N3"]))
    assert s.services["svc-auth"].path == ["N2", "N1", "N3"]


def test_path_must_start_at_host_node():
    with pytest.raises(ValidationError):
        NetworkState.model_validate(_with_path(["N1", "N3"]))  # host is N2


def test_path_hop_without_edge_rejected():
    with pytest.raises(ValidationError):
        NetworkState.model_validate(_with_path(["N2", "N6"]))  # no N2-N6 edge


def test_path_unknown_node_rejected():
    with pytest.raises(ValidationError):
        NetworkState.model_validate(_with_path(["N2", "N1", "N99"]))
