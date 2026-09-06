"""Human-readable, evidence-grounded network summaries for Aegis.

The deterministic generator is deliberately conservative: every statement comes
from telemetry and ranked diagnoses. An LLM may later rewrite this output for
different audiences, but it should receive only this structured evidence.
"""

from __future__ import annotations

from typing import Any

from diagnosis_engine import diagnose


CAUSE_LABELS = {
    "network_device_overload": "network-device overload",
    "link_failure": "a likely link failure",
    "network_congestion": "network congestion",
    "memory_exhaustion": "memory exhaustion",
    "node_or_interface_failure": "a node or interface failure",
    "routing_or_configuration_issue": "a routing or configuration issue",
}


def _n(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _format_metric(value: float | None, unit: str, decimals: int = 1) -> str | None:
    return f"{value:.{decimals}f} {unit}" if value is not None else None


def _node_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["node_id"]: node for node in payload.get("nodes", [])}


def _metric_sentence(node: dict[str, Any]) -> str | None:
    """Describe the clearest measurable impact at one affected node."""
    telemetry = node.get("telemetry", {})
    network = telemetry.get("network", {})
    cpu = _n(telemetry.get("cpu", {}).get("usage_percent"))
    memory = _n(telemetry.get("memory", {}).get("usage_percent"))
    latency = _n(network.get("latency_ms", {}).get("average"))
    loss = _n(network.get("packet_loss_percent", {}).get("value"))
    details = []
    if cpu is not None and cpu >= 75:
        details.append(f"CPU is {cpu:.1f}%")
    if memory is not None and memory >= 80:
        details.append(f"memory use is {memory:.1f}%")
    if latency is not None and latency >= 100:
        details.append(f"average latency is {latency:.1f} ms")
    if loss is not None and loss >= 1:
        details.append(f"packet loss is {loss:.2f}%")
    if not details:
        return None
    return "; ".join(details) + "."


def _affected_service_sentence(payload: dict[str, Any]) -> str | None:
    affected = []
    for service in payload.get("services", []):
        if service.get("status") not in {"degraded", "unhealthy"}:
            continue
        name = service.get("name", service.get("service_id", "service"))
        metrics = service.get("metrics", {})
        error_rate = _n(metrics.get("error_rate_percent"))
        availability = _n(metrics.get("availability_percent"))
        if error_rate is not None:
            affected.append(f"{name} is degraded with a {error_rate:.1f}% error rate")
        elif availability is not None:
            affected.append(f"{name} is degraded with {availability:.1f}% availability")
        else:
            affected.append(f"{name} is degraded")
    if not affected:
        return None
    return "Affected service: " + "; ".join(affected) + "."


def generate_network_summary(payload: dict[str, Any], diagnosis_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create dashboard-ready summaries from raw telemetry and diagnoses.

    Parameters
    ----------
    payload:
        Telemetry JSON produced by the simulator.
    diagnosis_report:
        Optional output from diagnosis_engine.diagnose(). If omitted, it is
        generated directly from ``payload``.

    Returns
    -------
    dict
        A JSON-serializable report containing a headline, executive summary,
        per-diagnosis summaries, evidence, and safe next checks.
    """
    diagnosis_report = diagnosis_report or diagnose(payload)
    nodes = _node_by_id(payload)
    hypotheses = diagnosis_report.get("hypotheses", [])
    top = diagnosis_report.get("most_likely_root_cause")
    incident = payload.get("incident", {})
    summary_lines: list[str] = []

    if top:
        targets = [target for target in top.get("affected_targets", []) if target in nodes]
        target_name = nodes[targets[0]].get("name", targets[0]) if targets else "the affected network path"
        cause = CAUSE_LABELS.get(top["root_cause"], top["root_cause"].replace("_", " "))
        confidence = top["confidence"]
        summary_lines.append(
            f"{target_name} is affected by {cause} ({confidence} confidence)."
        )
        if targets:
            detail = _metric_sentence(nodes[targets[0]])
            if detail:
                summary_lines.append(f"Observed impact: {detail}")
    else:
        summary_lines.append("No root-cause hypothesis could be formed from the available telemetry.")

    service_sentence = _affected_service_sentence(payload)
    if service_sentence:
        summary_lines.append(service_sentence)

    if top:
        summary_lines.append("Recommended next checks: " + " ".join(top.get("next_checks", [])[:2]))

    per_diagnosis = []
    for hypothesis in hypotheses:
        target_ids = [target for target in hypothesis.get("affected_targets", []) if target in nodes]
        target_names = [nodes[target].get("name", target) for target in target_ids]
        target_display = ", ".join(target_names) if target_names else "the affected path"
        cause = CAUSE_LABELS.get(hypothesis["root_cause"], hypothesis["root_cause"].replace("_", " "))
        per_diagnosis.append({
            "diagnosis_id": hypothesis["diagnosis_id"],
            "severity": "critical" if hypothesis["confidence_score"] >= 0.75 else "warning",
            "summary": f"{target_display}: {cause} is a {hypothesis['confidence']}-confidence explanation.",
            "evidence": hypothesis["supporting_evidence"],
            "uncertainty": hypothesis["contradicting_evidence"],
        })

    severity = diagnosis_report.get("overall_status", "healthy")
    incident_label = incident.get("incident_id", "Network")
    headline = (
        f"{incident_label}: {top['root_cause'].replace('_', ' ').title()}"
        if top else f"{incident_label}: Insufficient telemetry for diagnosis"
    )
    return {
        "incident_id": incident.get("incident_id"),
        "headline": headline,
        "status": severity,
        "executive_summary": " ".join(summary_lines),
        "diagnosis_summaries": per_diagnosis,
        "llm_grounding_data": {
            "headline": headline,
            "top_hypothesis": top,
            "affected_services": payload.get("services", []),
            "data_quality": payload.get("data_quality", {}),
            "instruction": "Rewrite for clarity only. Do not add causes, metrics, actions, or certainty not present in this data.",
        },
    }


if __name__ == "__main__":
    import json

    example_payload = {
        "incident": {"incident_id": "INC-1042"},
        "nodes": [{
            "node_id": "router-r3", "name": "Router R3", "node_type": "router",
            "health": {"status": "degraded"},
            "telemetry": {
                "cpu": {"usage_percent": 97.0},
                "memory": {"usage_percent": 65.0, "available_mb": 1024},
                "network": {
                    "latency_ms": {"average": 250.0, "baseline_average": 30.0},
                    "packet_loss_percent": {"value": 3.5},
                },
            },
            "interfaces": [{
                "interface_id": "router-r3:eth0", "admin_status": "up", "oper_status": "up",
                "utilization_percent": {"inbound": 96.0, "outbound": 72.0}, "drop_count": 540,
            }],
        }],
        "services": [{
            "service_id": "payment-api", "name": "Payment API", "status": "degraded",
            "metrics": {"error_rate_percent": 42.0},
        }],
    }
    print(json.dumps(generate_network_summary(example_payload), indent=2))
