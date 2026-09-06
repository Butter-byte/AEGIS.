"""Single entry point for the Aegis AI Diagnosis + Recovery Planner demo."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anomaly_detector import detect_anomalies
from diagnosis_engine import diagnose
from network_summary_generator import generate_network_summary
from recovery_planner import generate_recovery_plans
from recovery_plan_ranker import RecoveryPlanMetrics, rank_recovery_plans


def validate_telemetry(payload: dict[str, Any]) -> list[str]:
    """Small dependency-free validation; use telemetry_schema.json in production."""
    errors: list[str] = []
    for field in ("schema_version", "generated_at", "incident", "nodes"):
        if field not in payload:
            errors.append(f"Missing top-level field: {field}")
    if not isinstance(payload.get("nodes", []), list) or not payload.get("nodes"):
        errors.append("nodes must be a non-empty array")
    for index, node in enumerate(payload.get("nodes", [])):
        for field in ("node_id", "node_type", "telemetry"):
            if field not in node:
                errors.append(f"nodes[{index}] is missing {field}")
    return errors


def build_final_output(payload: dict[str, Any], pipeline_result: dict[str, Any]) -> dict[str, Any]:
    """Build the stable Diagnosis-module-to-Digital-Twin handoff contract."""
    incident = payload["incident"]
    ranked = pipeline_result["ranked_recovery_plans"]
    for position, plan in enumerate(ranked, start=1):
        plan["rank"] = position
    plan_groups = []
    for group in pipeline_result["recovery_plans"]["plan_groups"]:
        plan_groups.append({"diagnosis_id": group["diagnosis"]["diagnosis_id"], "plans": group["plans"]})
    return {
        "schema_version": "1.0",
        "output_id": f"diagnosis-{incident['incident_id']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "incident": {"incident_id": incident["incident_id"], "severity": incident["severity"], "status": incident["status"]},
        "network_summary": pipeline_result["network_summary"],
        "diagnosis": {
            "most_likely_root_cause": pipeline_result["diagnoses"]["most_likely_root_cause"],
            "hypotheses": pipeline_result["diagnoses"]["hypotheses"],
        },
        "recovery_plan_groups": plan_groups,
        "ranking": {
            "algorithm_version": "1.0",
            "weights": {"downtime": 0.30, "risk": 0.25, "speed": 0.20, "complexity": 0.15, "resource_utilization": 0.10},
            "ranked_plans": ranked,
        },
        "digital_twin_handoff": {
            "status": "pending_simulation",
            "plans_to_simulate": [plan["plan_id"] for plan in ranked if plan["eligible"]],
            "execution_rule": "No plan may execute until it passes Digital Twin simulation and receives a bounded Safety Engine approval.",
            "simulation_context": {"topology_version": payload.get("environment", {}).get("topology_version"), "collection_window": payload.get("collection_window")},
        },
        "data_quality": payload.get("data_quality", {}),
    }


def _fallback_estimate(plan: dict[str, Any]) -> dict[str, Any]:
    """Demo-only estimates; replace with Digital Twin estimates when available."""
    title = plan["title"].lower()
    if "throttle" in title or "prioritize" in title:
        return {"expected_downtime_seconds": 5, "recovery_time_seconds": 60, "risk": "low", "complexity": "simple", "additional_resource_utilization_percent": 5}
    if "shift" in title or "reroute" in title or "steer" in title or "failover" in title:
        return {"expected_downtime_seconds": 15, "recovery_time_seconds": 120, "risk": "medium", "complexity": "moderate", "additional_resource_utilization_percent": 30}
    if "restart" in title or "recover" in title or "repair" in title or "replace" in title or "increase" in title or "software" in title:
        return {"expected_downtime_seconds": 180, "recovery_time_seconds": 300, "risk": "high", "complexity": "complex", "additional_resource_utilization_percent": 40}
    return {"expected_downtime_seconds": 60, "recovery_time_seconds": 180, "risk": plan["risk"], "complexity": "moderate", "additional_resource_utilization_percent": 20}


def run_pipeline(payload: dict[str, Any], simulation_estimates: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run telemetry through detection, diagnosis, planning, ranking, and summary.

    ``simulation_estimates`` is an optional Digital Twin result keyed by
    ``plan_id``. Each value may provide expected downtime, recovery time, risk,
    complexity, resource utilization, and Digital Twin / safety results.
    """
    validation_errors = validate_telemetry(payload)
    if validation_errors:
        return {"status": "invalid_input", "validation_errors": validation_errors}

    anomalies = detect_anomalies(payload)
    diagnoses = diagnose(payload)
    plan_report = generate_recovery_plans(diagnoses)
    simulation_estimates = simulation_estimates or {}
    plans_to_rank: list[RecoveryPlanMetrics] = []
    estimate_sources: dict[str, str] = {}
    for group in plan_report["plan_groups"]:
        for plan in group["plans"]:
            estimate = simulation_estimates.get(plan["plan_id"])
            if estimate is None:
                estimate = _fallback_estimate(plan)
                estimate_sources[plan["plan_id"]] = "fallback_demo_estimate"
            else:
                estimate_sources[plan["plan_id"]] = "digital_twin_estimate"
            plans_to_rank.append(RecoveryPlanMetrics(
                plan_id=plan["plan_id"], title=plan["title"],
                expected_downtime_seconds=estimate["expected_downtime_seconds"],
                recovery_time_seconds=estimate["recovery_time_seconds"],
                risk=estimate.get("risk", plan["risk"]),
                complexity=estimate["complexity"],
                additional_resource_utilization_percent=estimate["additional_resource_utilization_percent"],
                digital_twin_passed=estimate.get("digital_twin_passed", True),
                safety_policy_passed=estimate.get("safety_policy_passed", True),
                rollback_available=estimate.get("rollback_available", bool(plan["rollback"])),
            ))
    ranked = []
    for item in rank_recovery_plans(plans_to_rank):
        result = item.__dict__.copy()
        result["estimate_source"] = estimate_sources[item.plan_id]
        ranked.append(result)
    pipeline_result = {
        "status": "ok",
        "anomalies": anomalies,
        "diagnoses": diagnoses,
        "recovery_plans": plan_report,
        "ranked_recovery_plans": ranked,
        "network_summary": generate_network_summary(payload, diagnoses),
        "safety_boundary": "Ranked plans are candidates only; Digital Twin and Safety Engine approval are mandatory before execution.",
    }
    pipeline_result["final_output"] = build_final_output(payload, pipeline_result)
    return pipeline_result


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    payload = json.loads((here / "sample_telemetry.json").read_text(encoding="utf-8"))
    print(json.dumps(run_pipeline(payload), indent=2))
