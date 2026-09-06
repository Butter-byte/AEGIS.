"""Rule-based network anomaly detector for Aegis.

This module intentionally uses no machine learning. It evaluates telemetry against
explicit warning/critical thresholds and returns explainable findings that an AI
diagnosis component can reason over.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal

Severity = Literal["warning", "critical"]


@dataclass(frozen=True)
class Finding:
    """One explainable anomaly observed in a node or link."""

    finding_id: str
    anomaly_type: str
    severity: Severity
    target_type: Literal["node", "interface", "link"]
    target_id: str
    observed_value: float | str
    unit: str | None
    threshold: float | str | None
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


DEFAULTS = {
    "cpu_warning_percent": 75.0,
    "cpu_critical_percent": 90.0,
    "memory_warning_percent": 80.0,
    "memory_critical_percent": 90.0,
    "latency_warning_ms": 100.0,
    "latency_critical_ms": 200.0,
    "latency_baseline_multiplier": 2.0,
    "packet_loss_warning_percent": 1.0,
    "packet_loss_critical_percent": 2.0,
    "utilization_warning_percent": 80.0,
    "utilization_critical_percent": 90.0,
    "min_available_memory_mb": 256.0,
    "stale_after_seconds": 120.0,
}


def _number(value: Any, default: float | None = None) -> float | None:
    """Return a numeric value or a safe default when telemetry is absent."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _severity(value: float, warning: float, critical: float) -> Severity | None:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return None


def _finding(
    anomaly_type: str,
    severity: Severity,
    target_type: Literal["node", "interface", "link"],
    target_id: str,
    observed_value: float | str,
    unit: str | None,
    threshold: float | str | None,
    message: str,
    **evidence: Any,
) -> Finding:
    return Finding(
        finding_id=f"{anomaly_type}:{target_id}",
        anomaly_type=anomaly_type,
        severity=severity,
        target_type=target_type,
        target_id=target_id,
        observed_value=observed_value,
        unit=unit,
        threshold=threshold,
        message=message,
        evidence={key: value for key, value in evidence.items() if value is not None},
    )


def detect_node_anomalies(node: dict[str, Any], limits: dict[str, float] | None = None) -> list[Finding]:
    """Evaluate one node from the Aegis telemetry JSON schema."""
    limits = {**DEFAULTS, **(limits or {})}
    node_id = node["node_id"]
    findings: list[Finding] = []

    # A dead or unreachable node is always a critical incident.
    health = node.get("health", {})
    health_status = health.get("status", "unknown")
    if health_status in {"unhealthy", "unreachable"}:
        findings.append(_finding(
            "dead_node", "critical", "node", node_id, health_status, None, "healthy",
            f"Node is {health_status} and cannot be relied on for network service.",
            health_score=health.get("score"), reasons=health.get("reasons", []),
        ))

    telemetry = node.get("telemetry", {})
    cpu = telemetry.get("cpu", {})
    cpu_usage = _number(cpu.get("usage_percent"))
    if cpu_usage is not None:
        warning = _number(cpu.get("warning_threshold_percent"), limits["cpu_warning_percent"])
        critical = _number(cpu.get("critical_threshold_percent"), limits["cpu_critical_percent"])
        sev = _severity(cpu_usage, warning, critical)
        if sev:
            findings.append(_finding(
                "high_cpu", sev, "node", node_id, cpu_usage, "percent",
                critical if sev == "critical" else warning,
                f"CPU usage is {cpu_usage:.1f}%, above the {sev} threshold.",
                baseline_percent=cpu.get("baseline_percent"),
            ))

    memory = telemetry.get("memory", {})
    memory_usage = _number(memory.get("usage_percent"))
    available_mb = _number(memory.get("available_mb"))
    if memory_usage is not None:
        warning = _number(memory.get("warning_threshold_percent"), limits["memory_warning_percent"])
        critical = _number(memory.get("critical_threshold_percent"), limits["memory_critical_percent"])
        sev = _severity(memory_usage, warning, critical)
        if sev:
            findings.append(_finding(
                "high_memory", sev, "node", node_id, memory_usage, "percent",
                critical if sev == "critical" else warning,
                f"Memory usage is {memory_usage:.1f}%, above the {sev} threshold.",
                available_mb=available_mb, baseline_percent=memory.get("baseline_percent"),
            ))
    if available_mb is not None and available_mb < limits["min_available_memory_mb"]:
        findings.append(_finding(
            "low_available_memory", "critical", "node", node_id, available_mb, "MB",
            limits["min_available_memory_mb"],
            f"Only {available_mb:.0f} MB of memory remains available.",
            memory_usage_percent=memory_usage,
        ))

    network = telemetry.get("network", {})
    latency = network.get("latency_ms", {})
    average_latency = _number(latency.get("average"))
    baseline_latency = _number(latency.get("baseline_average"))
    if average_latency is not None:
        latency_warning = limits["latency_warning_ms"]
        latency_critical = limits["latency_critical_ms"]
        # A route can have normally high latency. Flag it if it also doubles its own baseline.
        baseline_exceeded = (
            baseline_latency is not None
            and average_latency >= baseline_latency * limits["latency_baseline_multiplier"]
        )
        sev = _severity(average_latency, latency_warning, latency_critical)
        if sev or baseline_exceeded:
            severity: Severity = sev or "warning"
            threshold = latency_critical if severity == "critical" else latency_warning
            findings.append(_finding(
                "high_latency", severity, "node", node_id, average_latency, "ms", threshold,
                f"Average latency is {average_latency:.1f} ms"
                + (f", {average_latency / baseline_latency:.1f}x its baseline." if baseline_latency else "."),
                baseline_ms=baseline_latency, p95_ms=latency.get("p95"), p99_ms=latency.get("p99"),
            ))

    loss = network.get("packet_loss_percent", {})
    loss_value = _number(loss.get("value"))
    if loss_value is not None:
        warning = _number(loss.get("warning_threshold"), limits["packet_loss_warning_percent"])
        critical = _number(loss.get("critical_threshold"), limits["packet_loss_critical_percent"])
        sev = _severity(loss_value, warning, critical)
        if sev:
            findings.append(_finding(
                "packet_loss", sev, "node", node_id, loss_value, "percent",
                critical if sev == "critical" else warning,
                f"Packet loss is {loss_value:.2f}%, above the {sev} threshold.",
                baseline_percent=loss.get("baseline"),
            ))

    # Overloaded-router detection correlates CPU, packet loss, and interface saturation.
    interface_saturated = False
    for interface in node.get("interfaces", []):
        findings.extend(detect_interface_anomalies(interface, limits))
        util = interface.get("utilization_percent", {})
        interface_saturated |= any(
            (_number(util.get(direction), 0.0) or 0.0) >= limits["utilization_critical_percent"]
            for direction in ("inbound", "outbound")
        )

    overload_signals = sum([
        cpu_usage is not None and cpu_usage >= limits["cpu_critical_percent"],
        loss_value is not None and loss_value >= limits["packet_loss_warning_percent"],
        interface_saturated,
    ])
    if node.get("node_type") in {"router", "firewall", "load_balancer"} and overload_signals >= 2:
        findings.append(_finding(
            "overloaded_network_node", "critical", "node", node_id, overload_signals, "signals", 2,
            "Node shows multiple overload signals: high CPU, packet loss, and/or saturated interfaces.",
            cpu_usage_percent=cpu_usage, packet_loss_percent=loss_value,
            has_saturated_interface=interface_saturated,
        ))

    return findings


def detect_interface_anomalies(interface: dict[str, Any], limits: dict[str, float] | None = None) -> list[Finding]:
    """Evaluate a single node interface."""
    limits = {**DEFAULTS, **(limits or {})}
    interface_id = interface["interface_id"]
    findings: list[Finding] = []

    if interface.get("admin_status") == "up" and interface.get("oper_status") == "down":
        findings.append(_finding(
            "interface_down", "critical", "interface", interface_id, "down", None, "up",
            "Interface is administratively enabled but operationally down.",
            last_changed_at=interface.get("last_changed_at"),
        ))

    utilization = interface.get("utilization_percent", {})
    for direction in ("inbound", "outbound"):
        value = _number(utilization.get(direction))
        if value is None:
            continue
        sev = _severity(value, limits["utilization_warning_percent"], limits["utilization_critical_percent"])
        if sev:
            findings.append(_finding(
                f"high_bandwidth_utilization_{direction}", sev, "interface", interface_id, value, "percent",
                limits["utilization_critical_percent"] if sev == "critical" else limits["utilization_warning_percent"],
                f"{direction.title()} interface utilization is {value:.1f}%.",
                direction=direction, capacity_mbps=interface.get("capacity_mbps"),
            ))

    packet_loss = _number(interface.get("packet_loss_percent"))
    drop_count = _number(interface.get("drop_count"), 0.0) or 0.0
    error_count = _number(interface.get("error_count"), 0.0) or 0.0
    if packet_loss is not None:
        sev = _severity(packet_loss, limits["packet_loss_warning_percent"], limits["packet_loss_critical_percent"])
        if sev:
            findings.append(_finding(
                "interface_packet_loss", sev, "interface", interface_id, packet_loss, "percent",
                limits["packet_loss_critical_percent"] if sev == "critical" else limits["packet_loss_warning_percent"],
                f"Interface packet loss is {packet_loss:.2f}%.",
                drop_count=drop_count, error_count=error_count,
            ))

    # Congestion is a correlated condition, not merely high bandwidth use.
    max_utilization = max((_number(utilization.get("inbound"), 0.0) or 0.0), (_number(utilization.get("outbound"), 0.0) or 0.0))
    if (
        max_utilization >= limits["utilization_critical_percent"]
        and ((packet_loss or 0.0) >= limits["packet_loss_warning_percent"] or drop_count > 0)
    ):
        findings.append(_finding(
            "network_congestion", "critical", "interface", interface_id, max_utilization, "percent",
            limits["utilization_critical_percent"],
            "Interface is saturated and also dropping or losing packets, indicating congestion.",
            packet_loss_percent=packet_loss, drop_count=drop_count, error_count=error_count,
        ))

    return findings


def detect_link_anomalies(link: dict[str, Any], limits: dict[str, float] | None = None) -> list[Finding]:
    """Evaluate an explicit topology link, if the simulator sends link telemetry."""
    limits = {**DEFAULTS, **(limits or {})}
    link_id = link["link_id"]
    findings: list[Finding] = []
    if link.get("status") == "down":
        findings.append(_finding(
            "link_down", "critical", "link", link_id, "down", None, "up",
            "Link is down.",
            source=link.get("source_node_id"), destination=link.get("destination_node_id"),
        ))

    metrics = link.get("metrics", {})
    for metric, warning_key, critical_key, unit, anomaly_type in [
        ("latency_ms", "latency_warning_ms", "latency_critical_ms", "ms", "link_high_latency"),
        ("packet_loss_percent", "packet_loss_warning_percent", "packet_loss_critical_percent", "percent", "link_packet_loss"),
        ("utilization_percent", "utilization_warning_percent", "utilization_critical_percent", "percent", "link_high_utilization"),
    ]:
        value = _number(metrics.get(metric))
        if value is None:
            continue
        sev = _severity(value, limits[warning_key], limits[critical_key])
        if sev:
            findings.append(_finding(
                anomaly_type, sev, "link", link_id, value, unit,
                limits[critical_key] if sev == "critical" else limits[warning_key],
                f"Link {metric} is {value:.2f} {unit}.",
            ))
    return findings


def detect_anomalies(payload: dict[str, Any], limits: dict[str, float] | None = None) -> dict[str, Any]:
    """Return a JSON-serializable anomaly report for a full Aegis telemetry payload."""
    findings: list[Finding] = []
    for node in payload.get("nodes", []):
        findings.extend(detect_node_anomalies(node, limits))
    for link in payload.get("links", []):
        findings.extend(detect_link_anomalies(link, limits))

    findings.sort(key=lambda item: (item.severity != "critical", item.anomaly_type, item.target_id))
    critical_count = sum(item.severity == "critical" for item in findings)
    warning_count = sum(item.severity == "warning" for item in findings)
    return {
        "incident_id": payload.get("incident", {}).get("incident_id"),
        "schema_version": "1.0",
        "overall_status": "critical" if critical_count else "warning" if warning_count else "healthy",
        "summary": {
            "critical_count": critical_count,
            "warning_count": warning_count,
            "total_findings": len(findings),
        },
        "findings": [asdict(finding) for finding in findings],
    }


if __name__ == "__main__":
    # Replace this compact example with telemetry JSON from the simulator.
    example_payload = {
        "incident": {"incident_id": "INC-1042"},
        "nodes": [{
            "node_id": "router-r7",
            "node_type": "router",
            "health": {"status": "degraded", "score": 48},
            "telemetry": {
                "cpu": {"usage_percent": 92.4, "baseline_percent": 34.0},
                "memory": {"usage_percent": 71.0, "available_mb": 1180},
                "network": {
                    "latency_ms": {"average": 132.0, "baseline_average": 24.0},
                    "packet_loss_percent": {"value": 3.2},
                },
            },
            "interfaces": [{
                "interface_id": "router-r7:eth0",
                "admin_status": "up", "oper_status": "up", "capacity_mbps": 1000,
                "utilization_percent": {"inbound": 96.0, "outbound": 88.0},
                "packet_loss_percent": 2.8, "drop_count": 890, "error_count": 37,
            }],
        }],
    }
    import json
    print(json.dumps(detect_anomalies(example_payload), indent=2))
