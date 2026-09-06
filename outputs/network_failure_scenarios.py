"""Twenty deterministic simulator scenarios for testing the Aegis pipeline.

Run this file to emit a JSON artifact containing each telemetry input, expected
assertions, generated recovery plans/ranking, and final Digital Twin handoff.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from aegis_pipeline import run_pipeline


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    description: str
    telemetry_input: dict[str, Any]
    expected_anomalies: list[str]
    expected_root_cause: str


def base_payload(scenario_id: str, node_type: str = "router") -> dict[str, Any]:
    return {
        "schema_version": "1.0", "generated_at": "2026-09-06T14:05:00Z",
        "incident": {"incident_id": scenario_id, "status": "active", "severity": "high"},
        "nodes": [{
            "node_id": "node-a", "name": "Node A", "node_type": node_type,
            "health": {"status": "degraded", "score": 55},
            "telemetry": {
                "cpu": {"usage_percent": 35},
                "memory": {"usage_percent": 45, "available_mb": 2048},
                "network": {"latency_ms": {"average": 25, "baseline_average": 20}, "packet_loss_percent": {"value": 0.0}},
            },
            "interfaces": [{
                "interface_id": "node-a:eth0", "admin_status": "up", "oper_status": "up",
                "capacity_mbps": 1000, "utilization_percent": {"inbound": 30, "outbound": 20},
                "packet_loss_percent": 0.0, "error_count": 0, "drop_count": 0,
            }],
        }],
        "links": [], "services": [], "events": [],
        "data_quality": {"overall_status": "good", "missing_fields": [], "stale_sources": [], "simulator_mode": True},
    }


def node(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["nodes"][0]


def overload(scenario_id: str, title: str, *, node_type: str = "router", cpu: float = 95, latency: float = 180, loss: float = 2.5, util: float = 92) -> Scenario:
    p = base_payload(scenario_id, node_type)
    n = node(p); n["telemetry"]["cpu"]["usage_percent"] = cpu; n["telemetry"]["network"]["latency_ms"]["average"] = latency; n["telemetry"]["network"]["packet_loss_percent"]["value"] = loss; n["interfaces"][0]["utilization_percent"]["inbound"] = util; n["interfaces"][0]["drop_count"] = 100
    return Scenario(scenario_id, title, "High device CPU coincides with forwarding degradation.", p, ["high_cpu", "high_latency", "packet_loss", "overloaded_network_node"], "network_device_overload")


def congestion(scenario_id: str, title: str, *, util: float = 96, loss: float = 2.0, latency: float = 160) -> Scenario:
    p = base_payload(scenario_id)
    n = node(p); n["telemetry"]["network"]["latency_ms"]["average"] = latency; n["telemetry"]["network"]["packet_loss_percent"]["value"] = loss; n["interfaces"][0]["utilization_percent"]["inbound"] = util; n["interfaces"][0]["drop_count"] = 500
    return Scenario(scenario_id, title, "A saturated path is dropping packets and adding delay.", p, ["high_bandwidth_utilization_inbound", "network_congestion", "packet_loss"], "network_congestion")


def link_failure(scenario_id: str, title: str, *, down: bool = False) -> Scenario:
    p = base_payload(scenario_id)
    n = node(p); n["telemetry"]["network"]["packet_loss_percent"]["value"] = 4.0; n["interfaces"][0]["packet_loss_percent"] = 4.0; n["interfaces"][0]["error_count"] = 120
    if down: n["interfaces"][0]["oper_status"] = "down"
    anomalies = ["packet_loss", "interface_packet_loss"] + (["interface_down"] if down else [])
    return Scenario(scenario_id, title, "Loss and interface errors occur while CPU remains normal.", p, anomalies, "link_failure")


def memory_failure(scenario_id: str, title: str, *, available: float = 128) -> Scenario:
    p = base_payload(scenario_id)
    n = node(p); n["telemetry"]["memory"] = {"usage_percent": 94, "available_mb": available}; n["telemetry"]["network"]["latency_ms"]["average"] = 130
    return Scenario(scenario_id, title, "Critical memory pressure risks session and process failure.", p, ["high_memory", "low_available_memory", "high_latency"], "memory_exhaustion")


def routing_issue(scenario_id: str, title: str, *, event_type: str = "configuration_change") -> Scenario:
    p = base_payload(scenario_id)
    n = node(p); n["telemetry"]["network"]["latency_ms"]["average"] = 210; n["telemetry"]["network"]["packet_loss_percent"]["value"] = 1.2
    p["events"].append({"event_id": f"{scenario_id}-event", "timestamp": "2026-09-06T14:00:00Z", "source_id": "node-a", "event_type": event_type, "summary": f"Recent {event_type} before degradation."})
    return Scenario(scenario_id, title, "A route or policy event coincides with reachability degradation.", p, ["high_latency", "packet_loss"], "routing_or_configuration_issue")


def dead_node(scenario_id: str, title: str, *, status: str = "unreachable") -> Scenario:
    p = base_payload(scenario_id)
    n = node(p); n["health"] = {"status": status, "score": 0, "reasons": ["No health-check response"]}; n["interfaces"][0]["oper_status"] = "down"
    return Scenario(scenario_id, title, "A required network component no longer responds.", p, ["dead_node", "interface_down"], "node_or_interface_failure")


def scenarios() -> list[Scenario]:
    items = [
        overload("SCN-01", "Core router CPU overload"),
        overload("SCN-02", "Firewall inspection overload", node_type="firewall", cpu=96, latency=220, loss=2.2),
        link_failure("SCN-03", "Degrading fiber link"),
        link_failure("SCN-04", "Enabled interface unexpectedly down", down=True),
        congestion("SCN-05", "Primary WAN congestion"),
        congestion("SCN-06", "Backup link congestion after failover", util=98, loss=3.5, latency=240),
        memory_failure("SCN-07", "Router memory exhaustion"),
        dead_node("SCN-08", "Unreachable core router"),
        routing_issue("SCN-09", "Incorrect BGP policy change"),
        routing_issue("SCN-10", "BGP neighbor failure", event_type="routing_neighbor_down"),
        Scenario("SCN-11", "VPN gateway encryption overload", "VPN gateway CPU coincides with forwarding degradation.",
                 overload("SCN-11", "VPN gateway encryption overload", node_type="vpn_gateway", cpu=94, latency=190, loss=1.5).telemetry_input,
                 ["high_cpu", "high_latency", "packet_loss"], "network_device_overload"),
        overload("SCN-12", "DDoS-driven edge router overload", cpu=99, latency=300, loss=5.0, util=99),
        link_failure("SCN-13", "Faulty switch port with packet errors"),
        congestion("SCN-14", "Data-center east-west congestion", util=94, loss=1.5, latency=120),
        routing_issue("SCN-15", "Wrong static route deployment", event_type="route_change"),
        memory_failure("SCN-16", "Firewall session-table memory pressure", available=64),
        dead_node("SCN-17", "Failed load balancer", status="unhealthy"),
        overload("SCN-18", "Control-plane route storm", cpu=98, latency=150, loss=1.1, util=70),
        congestion("SCN-19", "Nightly backup saturating WAN", util=97, loss=2.8, latency=175),
        routing_issue("SCN-20", "Route flap after configuration rollback", event_type="route_change"),
    ]
    return items


def build_scenario_artifact() -> list[dict[str, Any]]:
    """Return all requested test data and the exact pipeline output for each case."""
    artifact = []
    for scenario in scenarios():
        result = run_pipeline(deepcopy(scenario.telemetry_input))
        artifact.append({
            "scenario_id": scenario.scenario_id,
            "title": scenario.title,
            "description": scenario.description,
            "telemetry_input": scenario.telemetry_input,
            "expected": {
                "anomaly_types": scenario.expected_anomalies,
                "most_likely_root_cause": scenario.expected_root_cause,
                "recovery_plan_count_rule": "2-5 candidate plans per diagnosis",
                "ranking_rule": "Eligible plans are sorted by descending final_score; Digital Twin/Safety failures are rejected."
            },
            "actual": {
                "anomaly_types": [finding["anomaly_type"] for finding in result["anomalies"]["findings"]],
                "most_likely_root_cause": result["diagnoses"]["most_likely_root_cause"]["root_cause"],
                "recovery_plans": result["recovery_plans"],
                "ranking": result["ranked_recovery_plans"],
                "final_output_json": result["final_output"]
            }
        })
    return artifact


if __name__ == "__main__":
    import json
    print(json.dumps(build_scenario_artifact(), indent=2))
