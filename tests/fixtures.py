"""Canonical valid instances of every shared contract.

The integration currency: every test builds from here rather than hand-rolling
instances that drift from docs/BACKEND_SCHEMA.md.

Aligned to the architecture on `integration`:
  * SimulationResult / SimMetrics / SimDelta live in backend.models.simulation
    and carry NO `id` (see BACKEND_SCHEMA.md §6.1).
  * Diagnosis has no `source` field.
  * RecoveryPlan.source is "llm" | "heuristic" (§5).
  * NodeTelemetry fields are cpu / latency / packet_loss / status (§3).
"""

from __future__ import annotations

from backend.models import (
    CandidateResult,
    Diagnosis,
    Fault,
    FaultRequest,
    NetworkState,
    RecoveryPlan,
    RecoveryRunResult,
    SafetyDecision,
    SimulationResult,
    Telemetry,
    Violation,
)
from backend.models.common import utcnow
from backend.models.enums import (
    EdgeStatus,
    FaultType,
    NodeStatus,
    RunOutcome,
    ServiceStatus,
    ViolationLevel,
)
from backend.models.simulation import SimDelta, SimMetrics
from backend.models.state import EdgeState, NodeState, ServiceState
from backend.models.telemetry import NodeTelemetry

DX_ID = "dx-00aa11bb"
PLAN_ID = "plan-00aa11bb"
RUN_ID = "run-00aa11bb"
FAULT_ID = "flt-00aa11bb"

_NODES = ["N1", "N2", "N3", "N4", "N5", "N6"]
_LINKS = [("N1", "N2"), ("N1", "N3"), ("N2", "N4"), ("N3", "N4"), ("N4", "N5"), ("N5", "N6")]


def network_state(version: int = 0) -> NetworkState:
    nodes = {
        nid: NodeState(
            id=nid, status=NodeStatus.healthy, cpu_percent=20.0, latency_ms=5.0,
            packet_loss_percent=0.0, capacity=1000.0, load=100.0,
        )
        for nid in _NODES
    }
    edges = [
        EdgeState(
            id=f"{a}-{b}", source=a, target=b, bandwidth_mbps=1000.0, latency_ms=5.0,
            packet_loss_percent=0.0, utilization_percent=10.0, status=EdgeStatus.active,
        )
        for a, b in _LINKS
    ]
    services = {
        "svc-auth": ServiceState(
            id="svc-auth", host_node="N2", required_bandwidth=100.0,
            status=ServiceStatus.running, path=["N2", "N1", "N3"],
        ),
        "svc-api": ServiceState(
            id="svc-api", host_node="N4", required_bandwidth=200.0,
            status=ServiceStatus.running, path=["N4", "N5", "N6"],
        ),
    }
    return NetworkState(
        version=version, updated_at=utcnow(), nodes=nodes, edges=edges,
        services=services, active_fault_ids=[],
    )


def node_state() -> NodeState:
    return NodeState(
        id="N1", status=NodeStatus.healthy, cpu_percent=20.0, latency_ms=5.0,
        packet_loss_percent=0.0, capacity=1000.0, load=100.0,
    )


def edge_state() -> EdgeState:
    return EdgeState(
        id="N1-N2", source="N1", target="N2", bandwidth_mbps=1000.0, latency_ms=5.0,
        packet_loss_percent=0.0, utilization_percent=10.0, status=EdgeStatus.active,
    )


def service_state() -> ServiceState:
    return ServiceState(
        id="svc-auth", host_node="N2", required_bandwidth=100.0,
        status=ServiceStatus.running, path=["N2", "N1", "N3"],
    )


def telemetry() -> Telemetry:
    return Telemetry(
        at=utcnow(), based_on_version=0, network_availability=1.0, avg_latency=10.0,
        max_latency=20.0, total_packet_loss=0.0, active_nodes=6, failed_nodes=0,
        quarantined_nodes=0, congested_edges=0, failed_edges=0,
        per_node={"N1": NodeTelemetry(cpu=20.0, latency=5.0, packet_loss=0.0, status=NodeStatus.healthy)},
    )


def fault() -> Fault:
    return Fault(id=FAULT_ID, type=FaultType.kill_node, target="N1", params={}, created_at=utcnow())


def fault_request() -> FaultRequest:
    return FaultRequest(type=FaultType.kill_node, target="N2")


def diagnosis() -> Diagnosis:
    return Diagnosis(
        id=DX_ID, created_at=utcnow(), based_on_version=0, summary="N2 down",
        suspected_nodes=["N2"], suspected_edges=[], suspected_services=["svc-auth"],
        confidence=0.9, rationale="node N2 reports failed status",
    )


def recovery_plan(based_on_version: int = 0) -> RecoveryPlan:
    return RecoveryPlan(
        id=PLAN_ID, created_at=utcnow(), based_on_version=based_on_version,
        targets_diagnosis=DX_ID, strategy_label="quarantine + migrate",
        rationale="isolate N2 and move its service to N3",
        actions=[
            {"type": "quarantine_node", "node_id": "N2"},
            {"type": "migrate_service", "service_id": "svc-auth", "to_node": "N3"},
        ],
        source="heuristic",
    )


def sim_metrics() -> SimMetrics:
    return SimMetrics(
        availability=1.0, avg_latency=11.0, max_latency=22.0, worst_node_load=0.3,
        unreachable_services=[], path_count=2,
    )


def simulation_result(feasible: bool = True) -> SimulationResult:
    if feasible:
        return SimulationResult(
            plan_id=PLAN_ID, based_on_version=0, feasible=True, metrics=sim_metrics(),
            delta=SimDelta(availability=0.0, avg_latency=1.0, max_latency=2.0), computed_at=utcnow(),
        )
    return SimulationResult(
        plan_id=PLAN_ID, based_on_version=0, feasible=False,
        infeasible_reason="no path for svc-auth", computed_at=utcnow(),
    )


def safety_decision(approved: bool = True) -> SafetyDecision:
    return SafetyDecision(
        plan_id=PLAN_ID, based_on_version=0, approved=approved,
        violations=[] if approved else [Violation(rule="availability_floor", detail="0.5 < 0.99", level=ViolationLevel.critical)],
        evaluated={"availability": 1.0}, policy_version="p0-scaffold", decided_at=utcnow(),
    )


def candidate_result() -> CandidateResult:
    return CandidateResult(plan=recovery_plan(), simulation=simulation_result(), safety=safety_decision())


def recovery_run_result() -> RecoveryRunResult:
    return RecoveryRunResult(
        run_id=RUN_ID, based_on_version=0, outcome=RunOutcome.applied, message="applied plan",
        diagnosis=diagnosis(), candidates=[candidate_result()], applied_plan_id=PLAN_ID,
        resulting_version=1, completed_at=utcnow(),
    )


ALL_FACTORIES = [
    network_state, node_state, edge_state, service_state, telemetry, fault, fault_request,
    diagnosis, recovery_plan, simulation_result, safety_decision, candidate_result,
    recovery_run_result,
]
