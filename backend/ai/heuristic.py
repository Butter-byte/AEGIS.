from __future__ import annotations

from backend.models.common import new_diagnosis_id, new_plan_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import NodeStatus
from backend.models.faults import Fault
from backend.models.recovery import MigrateServiceAction, QuarantineNodeAction, RecoveryPlan
from backend.models.state import NetworkState
from backend.models.telemetry import Telemetry


class HeuristicPlanner:
    def diagnose(self, state: NetworkState, active_faults: list[Fault], telemetry: Telemetry) -> Diagnosis:
        nodes = [fault.target for fault in active_faults if fault.target in state.nodes]
        nodes.extend(node.id for node in state.nodes.values() if node.status in {NodeStatus.failed, NodeStatus.degraded, NodeStatus.quarantined} and node.id not in nodes)
        edges = [fault.target for fault in active_faults if fault.target not in state.nodes]
        services = [service.id for service in state.services.values() if service.host_node in nodes]
        summary = "; ".join(f"{fault.type.value} at {fault.target}" for fault in active_faults) or "degraded network state"
        return Diagnosis(id=new_diagnosis_id(), created_at=utcnow(), based_on_version=state.version, summary=summary, suspected_nodes=nodes, suspected_edges=edges, suspected_services=services, confidence=0.9 if active_faults else 0.6, rationale=f"Telemetry reports {telemetry.failed_nodes} failed and {telemetry.quarantined_nodes} quarantined nodes.")

    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        plans: list[RecoveryPlan] = []
        for node_id in diagnosis.suspected_nodes:
            if node_id not in state.nodes:
                continue
            services = [service for service in state.services.values() if service.host_node == node_id]
            actions = [QuarantineNodeAction(node_id=node_id)]
            if services:
                target = next((node.id for node in state.nodes.values() if node.id != node_id and node.status == NodeStatus.healthy), None)
                if target:
                    actions = [MigrateServiceAction(service_id=service.id, to_node=target) for service in services] + [QuarantineNodeAction(node_id=node_id)]
            plans.append(RecoveryPlan(id=new_plan_id(), created_at=utcnow(), based_on_version=state.version, targets_diagnosis=diagnosis.id, strategy_label="isolate-and-relocate", rationale="Move affected services before isolating the unhealthy node.", actions=actions, source="heuristic"))
        return plans