"""Correlation of findings and events into ranked root-cause hypotheses."""

from __future__ import annotations

from typing import Any

from .models import Finding, Hypothesis


class DiagnosisEngine:
    def diagnose(self, telemetry: dict[str, Any], findings: list[Finding]) -> list[Hypothesis]:
        by_target: dict[str, list[Finding]] = {}
        for finding in findings: by_target.setdefault(finding.target_id.split(":")[0], []).append(finding)
        event_types = {event.get("source_id"): {event.get("event_type") for event in telemetry.get("events", [])} for event in telemetry.get("events", [])}
        hypotheses: list[Hypothesis] = []
        for node in telemetry.get("nodes", []):
            target = node["node_id"]; kinds = {finding.anomaly_type for finding in by_target.get(target, [])}; events = event_types.get(target, set())
            def add(cause: str, score: float, text: str, checks: list[str]):
                confidence = "high" if score >= .75 else "medium" if score >= .45 else "low"
                evidence = [finding.message for finding in by_target.get(target, [])]
                hypotheses.append(Hypothesis(f"{cause}:{target}", cause, score, confidence, [target], text, evidence, checks))
            if "dead_node" in kinds or "interface_down" in kinds: add("node_or_interface_failure", .95 if "dead_node" in kinds else .90, f"{target} is unavailable or has a failed enabled interface.", ["Check redundant path health.", "Inspect device and interface state."])
            if "high_memory" in kinds or "low_available_memory" in kinds: add("memory_exhaustion", .90 if "low_available_memory" in kinds else .70, f"{target} is under memory pressure.", ["Inspect memory trend and active sessions."])
            if "overloaded_network_node" in kinds: add("network_device_overload", .90, f"{target} shows correlated CPU and forwarding overload signals.", ["Inspect CPU consumers and top traffic flows."])
            if "network_congestion" in kinds: add("network_congestion", .85, f"A path around {target} is saturated and dropping traffic.", ["Identify top flows and alternate capacity."])
            if "packet_loss" in kinds and "high_cpu" not in kinds and "network_congestion" not in kinds: add("link_failure", .72, f"Loss near {target} occurs without CPU overload.", ["Compare interface errors and both link ends."])
            if events & {"route_change", "configuration_change", "routing_neighbor_down"} and ({"high_latency", "packet_loss"} & kinds): add("routing_or_configuration_issue", .82, f"A recent route/configuration event coincides with path degradation near {target}.", ["Compare current routes with the known-good version."])
        return sorted(hypotheses, key=lambda item: item.confidence_score, reverse=True)
