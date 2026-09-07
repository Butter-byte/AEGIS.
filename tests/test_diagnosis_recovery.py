"""Phase 3 — deterministic diagnoser + recovery planner.

Covers: root-cause classification, the closed recovery-action vocabulary,
effective-action preference, advisory/data-only boundaries, output-size bounds,
end-to-end behaviour through the wired pipeline, and no new runtime deps.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from backend.diagnosis import HeuristicDiagnoser
from backend.models.enums import EdgeStatus, NodeStatus
from backend.models.recovery import RecoveryAction, RecoveryPlan
from backend.models.validation import parse_plan
from backend.recovery import RecoveryPlanner
from backend.telemetry import TelemetryEngine
from tests import fixtures

_CLOSED_VOCAB = {
    "reroute", "drain_node", "restore_node", "migrate_service", "quarantine_node", "reset_link",
}
_EFFECTIVE = _CLOSED_VOCAB - {"reroute"}


def _diagnose(state, faults=()):
    telemetry = TelemetryEngine().derive(state)
    return HeuristicDiagnoser().diagnose(state, list(faults), telemetry)


def _with_node(status: NodeStatus, node_id="N2", **fields):
    state = fixtures.network_state()
    node = state.nodes[node_id]
    node.status = status
    for k, v in fields.items():
        setattr(node, k, v)
    return state


def _with_edge(status: EdgeStatus, **fields):
    state = fixtures.network_state()
    edge = state.edges[0]
    edge.status = status
    for k, v in fields.items():
        setattr(edge, k, v)
    return state, edge.id


# --- root-cause classification ---------------------------------------------

def test_node_failure_is_classified():
    dx = _diagnose(_with_node(NodeStatus.failed))
    assert dx.summary.startswith("Node or interface failure")
    assert dx.suspected_nodes == ["N2"]
    assert "svc-auth" in dx.suspected_services  # svc-auth is hosted on N2
    assert dx.confidence >= 0.75


def test_quarantined_node_is_node_failure():
    dx = _diagnose(_with_node(NodeStatus.quarantined))
    assert dx.summary.startswith("Node or interface failure")


def test_device_overload_is_classified():
    dx = _diagnose(_with_node(NodeStatus.degraded, node_id="N4", cpu_percent=95.0))
    assert dx.summary.startswith("Network device overload")
    assert dx.suspected_nodes == ["N4"]


def test_link_failure_is_classified():
    state, edge_id = _with_edge(EdgeStatus.failed)
    dx = _diagnose(state)
    assert dx.summary.startswith("Link failure")
    assert dx.suspected_edges == [edge_id]


def test_congestion_is_classified():
    state, edge_id = _with_edge(EdgeStatus.congested, utilization_percent=95.0)
    dx = _diagnose(state)
    assert dx.summary.startswith("Network congestion")
    assert dx.suspected_edges == [edge_id]


def test_healthy_network_yields_low_confidence_no_suspects():
    dx = _diagnose(fixtures.network_state())
    assert dx.suspected_nodes == [] and dx.suspected_edges == []
    assert dx.confidence < 0.5
    assert dx.summary  # still a valid, non-empty Diagnosis


def test_diagnosis_is_a_single_valid_canonical_object():
    dx = _diagnose(_with_node(NodeStatus.failed))
    assert dx.model_dump(mode="json")  # round-trips
    assert dx.based_on_version == 0
    assert 1 <= len(dx.summary) <= 500
    assert 1 <= len(dx.rationale) <= 2000


# --- closed recovery-action vocabulary ------------------------------------

_SCENARIOS = {
    "node_failure": lambda: _with_node(NodeStatus.failed),
    "overload": lambda: _with_node(NodeStatus.degraded, node_id="N4", cpu_percent=95.0),
    "link_failure": lambda: _with_edge(EdgeStatus.failed)[0],
    "congestion": lambda: _with_edge(EdgeStatus.congested, utilization_percent=95.0)[0],
}


@pytest.mark.parametrize("name", list(_SCENARIOS))
def test_planner_emits_only_closed_vocabulary(name):
    state = _SCENARIOS[name]()
    dx = _diagnose(state)
    plans = RecoveryPlanner().plan(state, dx)
    assert plans, f"{name}: expected at least one candidate plan"
    for plan in plans:
        assert isinstance(plan, RecoveryPlan)
        assert plan.source == "heuristic"
        assert plan.based_on_version == state.version
        assert 1 <= len(plan.actions) <= 6
        assert len(plan.strategy_label) <= 120
        assert len(plan.rationale) <= 2000
        for action in plan.actions:
            assert action.type in _CLOSED_VOCAB
        # survives the schema gate (referential integrity against the state)
        parse_plan(plan.model_dump(mode="json"), state)


def test_planner_rejects_no_custom_action_type():
    # sanity: the discriminated union itself refuses anything outside the six
    from pydantic import TypeAdapter, ValidationError

    with pytest.raises(ValidationError):
        TypeAdapter(RecoveryAction).validate_python({"operation": "restart_device", "target": "N2"})


# --- effective-action preference -----------------------------------------

@pytest.mark.parametrize("name", list(_SCENARIOS))
def test_every_plan_has_at_least_one_effective_action(name):
    state = _SCENARIOS[name]()
    plans = RecoveryPlanner().plan(state, _diagnose(state))
    for plan in plans:
        types = {a.type for a in plan.actions}
        assert types & _EFFECTIVE, f"{name}: plan {plan.strategy_label!r} is reroute-only (no-op)"


def test_service_host_failure_relocates_and_isolates():
    state = _with_node(NodeStatus.failed)  # N2 hosts svc-auth
    plans = RecoveryPlanner().plan(state, _diagnose(state))
    actions = [a.type for p in plans for a in p.actions]
    assert "migrate_service" in actions
    assert "quarantine_node" in actions


# --- advisory / data-only import boundaries -------------------------------

_BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
_FORBIDDEN = ("backend.state", "backend.execution", "backend.api", "backend.pipeline")


def _module_imports(pkg: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in (_BACKEND / pkg).rglob("*.py"):
        names: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)
        out[str(path.relative_to(_BACKEND))] = names
    return out


@pytest.mark.parametrize("pkg", ["diagnosis", "recovery"])
def test_package_is_advisory_and_data_only(pkg):
    for rel, imports in _module_imports(pkg).items():
        for imp in imports:
            assert not imp.startswith(_FORBIDDEN), (
                f"{rel} imports {imp} — {pkg}/ must never reach state / execution / "
                f"api / pipeline; it returns data only"
            )


@pytest.mark.parametrize("pkg", ["diagnosis", "recovery"])
def test_package_adds_no_third_party_dependency(pkg):
    allowed_non_backend = {"__future__"}
    for rel, imports in _module_imports(pkg).items():
        for imp in imports:
            root = imp.split(".")[0]
            assert imp.startswith("backend.") or root in allowed_non_backend, (
                f"{rel} imports {imp} — Phase 3 adds no runtime dependency"
            )


# --- end to end through the wired pipeline -------------------------------

@pytest.mark.parametrize("fault_type,target,expect", [
    ("kill_node", "N2", "Node or interface failure"),
    ("cut_edge", "__edge__", "Link failure"),
    ("congest_edge", "__edge__", "Network congestion"),
    ("overload_node", "N7", "Network device overload"),
])
def test_e2e_fault_diagnoses_and_recovers(wired_client, fault_type, target, expect):
    if target == "__edge__":
        target = wired_client.get("/network/state").json()["edges"][0]["id"]
    wired_client.post("/faults", json={"type": fault_type, "target": target})
    run = wired_client.post("/recovery/run").json()
    assert run["diagnosis"]["summary"].startswith(expect)
    assert run["outcome"] == "applied"
    assert run["applied_plan_id"] is not None

    if fault_type == "congest_edge":
        # the applied plan must actually clear the congestion, not just be "applied"
        applied = next(c["plan"] for c in run["candidates"] if c["plan"]["id"] == run["applied_plan_id"])
        assert any(a["type"] == "reset_link" for a in applied["actions"])
        edge = next(e for e in wired_client.get("/network/state").json()["edges"] if e["id"] == target)
        assert edge["status"] == "active"


def test_double_overload_yields_no_safe_plan(wired_client):
    """Real pipeline: two overloaded nodes -> every candidate leaves a node at
    load ratio 0.95, above the 0.90 Safety limit -> Safety rejects all of them ->
    no_safe_plan -> the Executor never runs -> network state is untouched.

    This is the deterministic proof that AEGIS does not blindly execute AI output.
    """
    v0 = wired_client.get("/network/state").json()["version"]

    wired_client.post("/faults", json={"type": "overload_node", "target": "N7"})
    wired_client.post("/faults", json={"type": "overload_node", "target": "N1"})
    v_fault = wired_client.get("/network/state").json()["version"]

    run = wired_client.post("/recovery/run").json()

    assert run["outcome"] == "no_safe_plan"
    assert run["applied_plan_id"] is None
    assert run["resulting_version"] is None
    assert len(run["candidates"]) >= 2
    for candidate in run["candidates"]:
        assert candidate["safety"]["approved"] is False
        assert any(
            v["rule"] == "node_load_limit" and v["level"] == "critical"
            for v in candidate["safety"]["violations"]
        )

    # the network was mutated only by the two fault injections, never by recovery
    assert wired_client.get("/network/state").json()["version"] == v_fault > v0
