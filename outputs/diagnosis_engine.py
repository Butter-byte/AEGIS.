"""Explainable, rule-based root-cause diagnosis for Aegis.

The engine consumes the simulator telemetry contract and the anomaly detector's
findings. It does not execute recovery actions; it produces ranked hypotheses
for the recovery planner and operator to inspect.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from anomaly_detector import DEFAULTS, detect_anomalies

Confidence = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Diagnosis:
    """A ranked root-cause hypothesis with auditable evidence."""

    diagnosis_id: str
    root_cause: str
    confidence_score: float
    confidence: Confidence
    affected_targets: list[str]
    explanation: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    next_checks: list[str]


def _n(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _confidence(score: float) -> Confidence:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _node_values(node: dict[str, Any]) -> dict[str, float | str]:
    telemetry = node.get("telemetry", {})
    network = telemetry.get("network", {})
    latency = network.get("latency_ms", {})
    memory = telemetry.get("memory", {})
    cpu = telemetry.get("cpu", {})
    loss = network.get("packet_loss_percent", {})
    max_utilization = 0.0
    total_drops = 0.0
    total_errors = 0.0
    interface_down = False
    for interface in node.get("interfaces", []):
        util = interface.get("utilization_percent", {})
        max_utilization = max(max_utilization, _n(util.get("inbound")), _n(util.get("outbound")))
        total_drops += _n(interface.get("drop_count"))
        total_errors += _n(interface.get("error_count"))
        interface_down |= interface.get("admin_status") == "up" and interface.get("oper_status") == "down"

    return {
        "cpu": _n(cpu.get("usage_percent")),
        "memory": _n(memory.get("usage_percent")),
        "available_memory_mb": _n(memory.get("available_mb"), float("inf")),
        "latency": _n(latency.get("average")),
        "latency_baseline": _n(latency.get("baseline_average")),
        "loss": _n(loss.get("value")),
        "max_utilization": max_utilization,
        "drops": total_drops,
        "errors": total_errors,
        "interface_down": interface_down,
        "health": node.get("health", {}).get("status", "unknown"),
    }


def _event_index(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for event in payload.get("events", []):
        source_id = event.get("source_id")
        if source_id:
            indexed.setdefault(source_id, []).append(event)
    return indexed


def _has_recent_event(events: list[dict[str, Any]], types: set[str]) -> list[dict[str, Any]]:
    """Events are assumed to be pre-filtered to the incident collection window."""
    return [event for event in events if event.get("event_type") in types]


def _diagnose_node(node: dict[str, Any], events: list[dict[str, Any]]) -> list[Diagnosis]:
    """Generate all plausible root-cause hypotheses for one node."""
    node_id = node["node_id"]
    node_type = node.get("node_type", "node")
    v = _node_values(node)
    diagnoses: list[Diagnosis] = []
    limits = DEFAULTS

    # 1. Node/device failure: directly reported as unavailable or with an enabled port down.
    if v["health"] in {"unhealthy", "unreachable"} or v["interface_down"]:
        evidence = []
        if v["health"] in {"unhealthy", "unreachable"}:
            evidence.append(f"Node health status is {v['health']}.")
        if v["interface_down"]:
            evidence.append("At least one administratively enabled interface is operationally down.")
        diagnoses.append(Diagnosis(
            diagnosis_id=f"node_or_interface_failure:{node_id}",
            root_cause="node_or_interface_failure",
            confidence_score=0.95 if v["health"] == "unreachable" else 0.90,
            confidence="high",
            affected_targets=[node_id],
            explanation=f"{node_type.title()} {node_id} is unavailable or has a failed enabled interface.",
            supporting_evidence=evidence,
            contradicting_evidence=[],
            next_checks=["Check device power, interface state, and physical/virtual link status.", "Confirm whether redundant paths are carrying traffic."],
        ))

    # 2. Router/firewall overload: multiple capacity symptoms should occur together.
    overload_signals = []
    if v["cpu"] >= limits["cpu_critical_percent"]:
        overload_signals.append(f"CPU is {v['cpu']:.1f}% (critical threshold: {limits['cpu_critical_percent']:.0f}%).")
    if v["latency"] >= limits["latency_warning_ms"]:
        overload_signals.append(f"Latency is {v['latency']:.1f} ms.")
    if v["loss"] >= limits["packet_loss_warning_percent"]:
        overload_signals.append(f"Packet loss is {v['loss']:.2f}%.")
    if v["max_utilization"] >= limits["utilization_critical_percent"]:
        overload_signals.append(f"An interface is {v['max_utilization']:.1f}% utilized.")
    if node_type in {"router", "firewall", "load_balancer", "vpn_gateway"} and v["cpu"] >= limits["cpu_critical_percent"] and len(overload_signals) >= 2:
        score = min(0.95, 0.60 + 0.10 * len(overload_signals))
        diagnoses.append(Diagnosis(
            diagnosis_id=f"network_device_overload:{node_id}",
            root_cause="network_device_overload",
            confidence_score=score,
            confidence=_confidence(score),
            affected_targets=[node_id],
            explanation=f"{node_type.title()} {node_id} is likely overloaded: high CPU coincides with forwarding-performance symptoms.",
            supporting_evidence=overload_signals,
            contradicting_evidence=[],
            next_checks=["Inspect top CPU-consuming processes or control-plane activity.", "Check for traffic spikes, DDoS indicators, or recent policy changes.", "Verify whether a redundant device can carry bounded traffic."],
        ))

    # 3. Link failure: loss/errors or an interface-down state with no CPU resource pressure.
    link_signals = []
    if v["loss"] >= limits["packet_loss_critical_percent"]:
        link_signals.append(f"Packet loss is {v['loss']:.2f}%.")
    if v["errors"] > 0:
        link_signals.append(f"Interfaces report {v['errors']:.0f} errors.")
    if v["interface_down"]:
        link_signals.append("An enabled interface is operationally down.")
    if len(link_signals) >= 1 and v["cpu"] < limits["cpu_warning_percent"]:
        score = 0.52 + 0.15 * len(link_signals)
        if v["interface_down"]:
            score += 0.18
        score = min(score, 0.95)
        diagnoses.append(Diagnosis(
            diagnosis_id=f"link_failure:{node_id}",
            root_cause="link_failure",
            confidence_score=score,
            confidence=_confidence(score),
            affected_targets=[node_id],
            explanation=f"A network link connected to {node_id} is likely failing or degraded, rather than the device being CPU-bound.",
            supporting_evidence=link_signals + [f"CPU is only {v['cpu']:.1f}%, below the overload warning threshold."],
            contradicting_evidence=[],
            next_checks=["Inspect the affected interface's optics/cable, error counters, and neighbor state.", "Compare loss from both ends of the link.", "Test a redundant path if available."],
        ))

    # 4. Congestion: saturation must be correlated with queues/loss/drops or excess delay.
    congestion_evidence = []
    if v["max_utilization"] >= limits["utilization_critical_percent"]:
        congestion_evidence.append(f"Interface utilization is {v['max_utilization']:.1f}%.")
    if v["loss"] >= limits["packet_loss_warning_percent"]:
        congestion_evidence.append(f"Packet loss is {v['loss']:.2f}%.")
    if v["drops"] > 0:
        congestion_evidence.append(f"Interfaces dropped {v['drops']:.0f} packets.")
    if v["latency"] >= limits["latency_warning_ms"]:
        congestion_evidence.append(f"Latency is {v['latency']:.1f} ms.")
    if v["max_utilization"] >= limits["utilization_critical_percent"] and len(congestion_evidence) >= 2:
        score = min(0.92, 0.55 + 0.10 * len(congestion_evidence))
        diagnoses.append(Diagnosis(
            diagnosis_id=f"network_congestion:{node_id}",
            root_cause="network_congestion",
            confidence_score=score,
            confidence=_confidence(score),
            affected_targets=[node_id],
            explanation=f"Traffic around {node_id} is likely congested: the path is saturated and service-quality metrics are degrading.",
            supporting_evidence=congestion_evidence,
            contradicting_evidence=[],
            next_checks=["Identify the top traffic flows on the saturated interface.", "Check whether failover moved traffic onto a smaller path.", "Validate available capacity on alternate paths."],
        ))

    # 5. Memory exhaustion: resource pressure can explain reboots, slow control plane, and failed sessions.
    memory_evidence = []
    if v["memory"] >= limits["memory_critical_percent"]:
        memory_evidence.append(f"Memory use is {v['memory']:.1f}%.")
    if v["available_memory_mb"] < limits["min_available_memory_mb"]:
        memory_evidence.append(f"Only {v['available_memory_mb']:.0f} MB of memory remains available.")
    if len(memory_evidence) >= 1:
        score = 0.70 if len(memory_evidence) == 1 else 0.90
        diagnoses.append(Diagnosis(
            diagnosis_id=f"memory_exhaustion:{node_id}",
            root_cause="memory_exhaustion",
            confidence_score=score,
            confidence=_confidence(score),
            affected_targets=[node_id],
            explanation=f"{node_type.title()} {node_id} is under severe memory pressure.",
            supporting_evidence=memory_evidence,
            contradicting_evidence=[],
            next_checks=["Check memory trend and process-level usage for a leak.", "Inspect active connection/session counts and route-table growth.", "Confirm a tested restart or failover procedure before any intervention."],
        ))

    # 6. Routing/configuration issue: a relevant event plus path quality degradation.
    routing_events = _has_recent_event(events, {"route_change", "configuration_change", "routing_neighbor_down"})
    routing_evidence = []
    if routing_events:
        routing_evidence.extend(f"Recent {event['event_type']}: {event.get('summary', 'no summary')}" for event in routing_events)
    if v["latency"] >= limits["latency_warning_ms"]:
        routing_evidence.append(f"Latency is elevated at {v['latency']:.1f} ms.")
    if v["loss"] >= limits["packet_loss_warning_percent"]:
        routing_evidence.append(f"Packet loss is elevated at {v['loss']:.2f}%.")
    if routing_events and len(routing_evidence) >= 2:
        score = min(0.88, 0.50 + 0.12 * len(routing_evidence))
        contradictions = []
        if v["cpu"] >= limits["cpu_critical_percent"]:
            contradictions.append("Critical CPU also supports device overload, so routing is not the only plausible cause.")
        diagnoses.append(Diagnosis(
            diagnosis_id=f"routing_or_configuration_issue:{node_id}",
            root_cause="routing_or_configuration_issue",
            confidence_score=score,
            confidence=_confidence(score),
            affected_targets=[node_id],
            explanation=f"A recent routing or configuration event near {node_id} coincides with path degradation.",
            supporting_evidence=routing_evidence,
            contradicting_evidence=contradictions,
            next_checks=["Compare current routes and policy with the last known-good version.", "Trace the path to affected prefixes through primary and backup routes.", "Validate the proposed change in the Digital Twin before rollback or rerouting."],
        ))

    return diagnoses


def diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    """Create ranked, JSON-serializable diagnoses for a full simulator payload."""
    event_by_source = _event_index(payload)
    hypotheses: list[Diagnosis] = []
    for node in payload.get("nodes", []):
        hypotheses.extend(_diagnose_node(node, event_by_source.get(node["node_id"], [])))

    # Link status may be present without being duplicated in a node's interfaces.
    for link in payload.get("links", []):
        if link.get("status") == "down":
            link_id = link["link_id"]
            hypotheses.append(Diagnosis(
                diagnosis_id=f"link_failure:{link_id}",
                root_cause="link_failure",
                confidence_score=0.95,
                confidence="high",
                affected_targets=[link_id, link.get("source_node_id", ""), link.get("destination_node_id", "")],
                explanation=f"Link {link_id} is explicitly reported as down.",
                supporting_evidence=["Link status is down."],
                contradicting_evidence=[],
                next_checks=["Verify both link endpoints and failover path health."],
            ))

    hypotheses.sort(key=lambda diagnosis: diagnosis.confidence_score, reverse=True)
    anomaly_report = detect_anomalies(payload)
    return {
        "incident_id": payload.get("incident", {}).get("incident_id"),
        "diagnosis_engine_version": "1.0",
        "overall_status": anomaly_report["overall_status"],
        "anomaly_summary": anomaly_report["summary"],
        "most_likely_root_cause": asdict(hypotheses[0]) if hypotheses else None,
        "hypotheses": [asdict(hypothesis) for hypothesis in hypotheses],
        "diagnosis_note": (
            "Hypotheses are evidence-based and ranked; they are not execution approvals. "
            "Validate a recovery plan in the Digital Twin and Safety Engine."
        ),
    }


if __name__ == "__main__":
    # A configuration event plus overload conditions deliberately creates two
    # plausible hypotheses; the evidence makes the trade-off explicit.
    import json

    example_payload = {
        "incident": {"incident_id": "INC-1042"},
        "nodes": [{
            "node_id": "router-r7", "node_type": "router",
            "health": {"status": "degraded"},
            "telemetry": {
                "cpu": {"usage_percent": 92.4},
                "memory": {"usage_percent": 71.0, "available_mb": 1180},
                "network": {
                    "latency_ms": {"average": 132.0, "baseline_average": 24.0},
                    "packet_loss_percent": {"value": 3.2},
                },
            },
            "interfaces": [{
                "interface_id": "router-r7:eth0", "admin_status": "up", "oper_status": "up",
                "utilization_percent": {"inbound": 96.0, "outbound": 88.0},
                "drop_count": 890, "error_count": 37,
            }],
        }],
        "events": [{
            "source_id": "router-r7", "event_type": "configuration_change",
            "summary": "BGP policy changed immediately before the incident.",
        }],
    }
    print(json.dumps(diagnose(example_payload), indent=2))
