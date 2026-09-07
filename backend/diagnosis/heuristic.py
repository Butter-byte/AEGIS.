"""Deterministic heuristic diagnoser — output of backend/diagnosis/ (Yyash).

Produces exactly one canonical `Diagnosis` from canonical inputs
(`NetworkState`, active `Fault`s, `Telemetry`). Advisory / data-only: this module
imports nothing from `backend.state`, `backend.execution`, `backend.api`, or
`backend.pipeline` and never mutates anything (architecture invariant 3/10,
enforced by tests/test_architecture_boundaries.py).

Root-cause taxonomy adapted from the `origin/diagnosis-engine` prototype. Only
the four causes derivable from canonical AEGIS telemetry are classified here:

    node_or_interface_failure   a node is failed / quarantined (unreachable)
    link_failure                an edge is failed (loss without device overload)
    network_device_overload     a node is degraded under CPU / forwarding load
    network_congestion          an edge is congested / near-saturated

`memory_exhaustion` and `routing_or_configuration_issue` need telemetry AEGIS
does not model (node memory, an events stream) and are intentionally omitted —
see the Phase 3 reconnaissance report.
"""

from __future__ import annotations

from backend.models.common import new_diagnosis_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import EdgeStatus, NodeStatus
from backend.models.faults import Fault
from backend.models.state import NetworkState
from backend.models.telemetry import Telemetry

# Thresholds carried over from the prototype's LIMITS table.
CPU_CRITICAL = 90.0
LOAD_RATIO_CRITICAL = 0.90
LOSS_CRITICAL = 20.0
UTIL_CRITICAL = 90.0

_DOWN_NODE = {NodeStatus.failed, NodeStatus.quarantined}

# root_cause -> (human label, confirmation check) — folded into summary / rationale
# since Diagnosis has no dedicated root_cause field this phase.
_CAUSE = {
    "node_or_interface_failure": (
        "Node or interface failure",
        "Confirm device power / peer state and check for a redundant path.",
    ),
    "link_failure": (
        "Link failure",
        "Compare both link ends, interface errors, and optics / cable / neighbour state.",
    ),
    "network_device_overload": (
        "Network device overload",
        "Inspect top CPU consumers and traffic flows for a spike or control-plane storm.",
    ),
    "network_congestion": (
        "Network congestion",
        "Identify the top flows on the saturated link and available alternate-path capacity.",
    ),
}


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class HeuristicDiagnoser:
    """Rule-based diagnoser wired as the pipeline's `diagnoser` port."""

    def diagnose(
        self,
        state: NetworkState,
        active_faults: list[Fault],
        telemetry: Telemetry,
    ) -> Diagnosis:
        down_nodes = [n.id for n in state.nodes.values() if n.status in _DOWN_NODE]
        failed_edges = [e.id for e in state.edges if e.status == EdgeStatus.failed]
        overloaded_nodes = [
            n.id
            for n in state.nodes.values()
            if n.status == NodeStatus.degraded
            and (n.cpu_percent >= CPU_CRITICAL or _load_ratio(n) >= LOAD_RATIO_CRITICAL)
        ]
        congested_edges = [
            e.id
            for e in state.edges
            if e.status == EdgeStatus.congested or e.utilization_percent >= UTIL_CRITICAL
        ]
        degraded_nodes = [
            n.id for n in state.nodes.values()
            if n.status == NodeStatus.degraded and n.id not in overloaded_nodes
        ]

        # first match wins, most service-affecting first
        if down_nodes:
            cause, nodes, edges = "node_or_interface_failure", sorted(down_nodes), []
        elif failed_edges:
            cause, nodes, edges = "link_failure", [], sorted(failed_edges)
        elif overloaded_nodes:
            cause, nodes, edges = "network_device_overload", sorted(overloaded_nodes), []
        elif congested_edges:
            cause, nodes, edges = "network_congestion", [], sorted(congested_edges)
        elif degraded_nodes:
            # a soft degradation with no clear overload signal — still worth flagging
            cause, nodes, edges = "network_device_overload", sorted(degraded_nodes), []
        else:
            cause, nodes, edges = None, [], []

        services = self._affected_services(state, nodes, edges)
        fault_targets = {f.target for f in active_faults}
        corroborated = bool(fault_targets & (set(nodes) | set(edges)))

        if cause is None:
            summary = "No actionable fault detected"
            rationale = (
                f"network_availability={telemetry.network_availability:.2f}; "
                f"{telemetry.failed_nodes} failed / {telemetry.quarantined_nodes} quarantined nodes, "
                f"{telemetry.failed_edges} failed / {telemetry.congested_edges} congested edges. "
                "No node or link meets a warning threshold."
            )
            confidence = 0.2
        else:
            label, check = _CAUSE[cause]
            targets = ", ".join(nodes + edges) or "the network"
            summary = f"{label}: {targets}"
            confidence = self._confidence(cause, corroborated)
            rationale = self._rationale(
                label, check, nodes, edges, services, telemetry, corroborated
            )

        return Diagnosis(
            id=new_diagnosis_id(),
            created_at=utcnow(),
            based_on_version=state.version,
            summary=_clip(summary, 500),
            suspected_nodes=nodes,
            suspected_edges=edges,
            suspected_services=services,
            confidence=confidence,
            rationale=_clip(rationale, 2000),
        )

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _affected_services(
        state: NetworkState, nodes: list[str], edges: list[str]
    ) -> list[str]:
        suspect_nodes, suspect_edges = set(nodes), set(edges)
        hit: set[str] = set()
        for svc in state.services.values():
            if svc.host_node in suspect_nodes:
                hit.add(svc.id)
                continue
            for a, b in zip(svc.path, svc.path[1:]):
                if _edge_id(a, b) in suspect_edges:
                    hit.add(svc.id)
                    break
        return sorted(hit)

    @staticmethod
    def _confidence(cause: str, corroborated: bool) -> float:
        if corroborated:
            return 0.9
        return {
            "node_or_interface_failure": 0.8,
            "link_failure": 0.75,
            "network_device_overload": 0.7,
            "network_congestion": 0.65,
        }[cause]

    @staticmethod
    def _rationale(
        label: str,
        check: str,
        nodes: list[str],
        edges: list[str],
        services: list[str],
        telemetry: Telemetry,
        corroborated: bool,
    ) -> str:
        parts = [
            f"{label} inferred from network state.",
            f"Telemetry: availability={telemetry.network_availability:.2f}, "
            f"avg_latency={telemetry.avg_latency:.1f}ms, max_latency={telemetry.max_latency:.1f}ms, "
            f"failed_nodes={telemetry.failed_nodes}, quarantined_nodes={telemetry.quarantined_nodes}, "
            f"failed_edges={telemetry.failed_edges}, congested_edges={telemetry.congested_edges}.",
        ]
        if nodes:
            parts.append("Suspected node(s): " + ", ".join(
                f"{nid} ({_node_metric(telemetry, nid)})" for nid in nodes
            ) + ".")
        if edges:
            parts.append("Suspected edge(s): " + ", ".join(edges) + ".")
        if services:
            parts.append("Impacted service(s): " + ", ".join(services) + ".")
        else:
            parts.append("No hosted or transiting service is currently impacted.")
        parts.append(
            "Corroborated by an active fault record." if corroborated
            else "No matching fault record; classification is telemetry-only."
        )
        parts.append(f"Next check: {check}")
        return " ".join(parts)


def _load_ratio(node) -> float:
    return node.load / node.capacity if node.capacity else 0.0


def _edge_id(a: str, b: str) -> str:
    lo, hi = sorted((a, b))
    return f"{lo}-{hi}"


def _node_metric(telemetry: Telemetry, node_id: str) -> str:
    nt = telemetry.per_node.get(node_id)
    if nt is None:
        return "no telemetry"
    return f"cpu={nt.cpu:.0f}%, loss={nt.packet_loss * 100:.0f}%, status={nt.status.value}"
