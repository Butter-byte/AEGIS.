"""Deterministic metric threshold evaluation."""

from __future__ import annotations

from typing import Any

from .models import Finding

LIMITS = {"cpu_warning": 75, "cpu_critical": 90, "memory_warning": 80, "memory_critical": 90, "min_memory_mb": 256, "latency_warning": 100, "latency_critical": 200, "loss_warning": 1, "loss_critical": 2, "util_warning": 80, "util_critical": 90}


def _number(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _severity(value: float, warning: float, critical: float) -> str | None:
    return "critical" if value >= critical else "warning" if value >= warning else None


class AnomalyDetector:
    def detect(self, telemetry: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []
        for node in telemetry.get("nodes", []):
            target = node["node_id"]; metrics = node.get("telemetry", {}); network = metrics.get("network", {})
            cpu = _number(metrics.get("cpu", {}).get("usage_percent")); memory = _number(metrics.get("memory", {}).get("usage_percent")); available = _number(metrics.get("memory", {}).get("available_mb"), 999999); latency = _number(network.get("latency_ms", {}).get("average")); loss = _number(network.get("packet_loss_percent", {}).get("value"))
            if node.get("health", {}).get("status") in {"unhealthy", "unreachable"}:
                findings.append(Finding("dead_node", "critical", target, node["health"]["status"], "healthy", "Node health check failed."))
            for kind, value, warning, critical, unit in [("high_cpu", cpu, LIMITS["cpu_warning"], LIMITS["cpu_critical"], "percent"), ("high_memory", memory, LIMITS["memory_warning"], LIMITS["memory_critical"], "percent"), ("high_latency", latency, LIMITS["latency_warning"], LIMITS["latency_critical"], "ms"), ("packet_loss", loss, LIMITS["loss_warning"], LIMITS["loss_critical"], "percent")]:
                severity = _severity(value, warning, critical)
                if severity: findings.append(Finding(kind, severity, target, value, critical if severity == "critical" else warning, f"{kind.replace('_', ' ')} is {value:.1f} {unit}."))
            if available < LIMITS["min_memory_mb"]:
                findings.append(Finding("low_available_memory", "critical", target, available, LIMITS["min_memory_mb"], f"Only {available:.0f} MB remains available."))
            overloaded_signals = int(cpu >= LIMITS["cpu_critical"]) + int(loss >= LIMITS["loss_warning"])
            for interface in node.get("interfaces", []):
                interface_id = interface["interface_id"]; util = max(_number(interface.get("utilization_percent", {}).get("inbound")), _number(interface.get("utilization_percent", {}).get("outbound"))); drops = _number(interface.get("drop_count")); errors = _number(interface.get("error_count")); interface_loss = _number(interface.get("packet_loss_percent"))
                if interface.get("admin_status") == "up" and interface.get("oper_status") == "down": findings.append(Finding("interface_down", "critical", interface_id, "down", "up", "Enabled interface is down."))
                sev = _severity(util, LIMITS["util_warning"], LIMITS["util_critical"])
                if sev: findings.append(Finding("high_bandwidth_utilization", sev, interface_id, util, LIMITS["util_critical"] if sev == "critical" else LIMITS["util_warning"], f"Interface utilization is {util:.1f}%"))
                if util >= LIMITS["util_critical"]: overloaded_signals += 1
                if interface_loss >= LIMITS["loss_warning"]: findings.append(Finding("interface_packet_loss", _severity(interface_loss, LIMITS["loss_warning"], LIMITS["loss_critical"]) or "warning", interface_id, interface_loss, LIMITS["loss_warning"], "Interface packet loss is elevated."))
                if util >= LIMITS["util_critical"] and (interface_loss >= LIMITS["loss_warning"] or drops > 0): findings.append(Finding("network_congestion", "critical", interface_id, util, LIMITS["util_critical"], "Saturation coincides with loss or drops.", {"drops": drops, "errors": errors}))
            if node.get("node_type") in {"router", "firewall", "load_balancer", "vpn_gateway"} and overloaded_signals >= 2: findings.append(Finding("overloaded_network_node", "critical", target, overloaded_signals, 2, "Multiple overload indicators are present."))
        return findings
