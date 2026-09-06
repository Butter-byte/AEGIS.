from __future__ import annotations

from backend.models.common import utcnow
from backend.models.enums import EdgeStatus, NodeStatus
from backend.models.state import NetworkState
from backend.models.telemetry import NodeTelemetry, Telemetry


class TelemetryEngine:
    def derive(self, state: NetworkState) -> Telemetry:
        nodes = list(state.nodes.values())
        active = [node for node in nodes if node.status not in {NodeStatus.failed, NodeStatus.quarantined}]
        latencies = [node.latency_ms for node in active]
        total_loss = sum(node.packet_loss_percent for node in nodes) / max(len(nodes), 1) / 100.0
        per_node = {
            node.id: NodeTelemetry(cpu=node.cpu_percent, latency=node.latency_ms, packet_loss=node.packet_loss_percent / 100.0, status=node.status)
            for node in nodes
        }
        return Telemetry(
            at=utcnow(), based_on_version=state.version,
            network_availability=len(active) / max(len(nodes), 1),
            avg_latency=sum(latencies) / max(len(latencies), 1), max_latency=max(latencies, default=0.0),
            total_packet_loss=min(total_loss, 1.0), active_nodes=len(active),
            failed_nodes=sum(node.status == NodeStatus.failed for node in nodes),
            quarantined_nodes=sum(node.status == NodeStatus.quarantined for node in nodes),
            congested_edges=sum(edge.status == EdgeStatus.congested for edge in state.edges),
            failed_edges=sum(edge.status == EdgeStatus.failed for edge in state.edges), per_node=per_node,
        )