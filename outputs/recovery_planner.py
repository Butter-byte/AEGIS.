"""Safety-aware, rule-based recovery planner for Aegis.

The planner converts ranked diagnosis hypotheses into 2-5 candidate recovery
plans per diagnosis. Plans are declarative action intents, not raw router CLI
commands, and must be validated by the Digital Twin and Safety Engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from diagnosis_engine import diagnose

Risk = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class RecoveryPlan:
    plan_id: str
    diagnosis_id: str
    title: str
    objective: str
    rationale: str
    risk: Risk
    requires_human_approval: bool
    actions: list[dict[str, Any]]
    preconditions: list[str]
    verification: list[str]
    stop_conditions: list[str]
    rollback: list[dict[str, Any]]


def _action(operation: str, target: str, **parameters: Any) -> dict[str, Any]:
    """A constrained action intent for a trusted device-specific adapter."""
    return {"operation": operation, "target": target, "parameters": parameters}


def _plan(
    diagnosis: dict[str, Any], suffix: str, title: str, objective: str, rationale: str,
    risk: Risk, requires_human_approval: bool, actions: list[dict[str, Any]],
    preconditions: list[str], verification: list[str], stop_conditions: list[str],
    rollback: list[dict[str, Any]],
) -> RecoveryPlan:
    return RecoveryPlan(
        plan_id=f"{diagnosis['diagnosis_id']}:plan-{suffix}",
        diagnosis_id=diagnosis["diagnosis_id"], title=title, objective=objective,
        rationale=rationale, risk=risk, requires_human_approval=requires_human_approval,
        actions=actions, preconditions=preconditions, verification=verification,
        stop_conditions=stop_conditions, rollback=rollback,
    )


def _target(diagnosis: dict[str, Any]) -> str:
    return next((item for item in diagnosis.get("affected_targets", []) if item), "unknown-target")


def plans_for_network_device_overload(diagnosis: dict[str, Any]) -> list[RecoveryPlan]:
    target = _target(diagnosis)
    return [
        _plan(diagnosis, "a", "Shift bounded traffic to a healthy peer", "Reduce load on the overloaded device.",
              "Moving a limited share of traffic to a healthy redundant path reduces CPU and queue pressure without taking the device offline.",
              "medium", False,
              [_action("validate_backup_capacity", target, minimum_headroom_percent=30), _action("shift_traffic", target, maximum_percent=25, destination="healthy_redundant_path")],
              ["A redundant path is healthy.", "Digital Twin predicts backup utilization below 80%.", "Traffic shift is permitted by policy."],
              ["CPU falls below 75%.", "Packet loss stays below 1%.", "Affected-service error rate improves."],
              ["Backup utilization exceeds 85%.", "A second region becomes unhealthy."],
              [_action("restore_traffic_distribution", target, previous_state="captured_before_execution")]),
        _plan(diagnosis, "b", "Throttle non-critical traffic", "Preserve capacity for critical services.",
              "Rate-limiting bulk, low-priority, or suspicious traffic frees processing and link capacity for important flows.",
              "medium", False,
              [_action("classify_traffic", target, classes=["critical", "bulk", "best_effort"]), _action("apply_rate_limit", target, traffic_class="bulk", maximum_percent_of_link=20)],
              ["Critical services and traffic classes are defined.", "Policy allows traffic shaping.", "Digital Twin confirms critical traffic retains required capacity."],
              ["Critical service latency and loss improve.", "CPU and interface drops decline."],
              ["Critical-service error rate increases.", "The traffic classifier behaves unexpectedly."],
              [_action("remove_rate_limit", target, traffic_class="bulk")]),
        _plan(diagnosis, "c", "Contain suspected abnormal traffic", "Remove traffic causing exceptional device load.",
              "A traffic spike or attack can overwhelm CPU; applying an approved containment policy can reduce the source of load.",
              "high", True,
              [_action("identify_top_talkers", target), _action("apply_temporary_containment_policy", target, scope="approved_suspicious_sources", duration_minutes=15)],
              ["Suspicious sources are identified using read-only evidence.", "Containment scope is reviewed by an operator.", "Digital Twin predicts no block of critical traffic."],
              ["CPU, drops, and packet loss decline.", "Legitimate traffic remains healthy."],
              ["Critical source is blocked.", "Packet loss or service errors worsen."],
              [_action("remove_temporary_containment_policy", target)]),
        _plan(diagnosis, "d", "Controlled failover and restart", "Restore a device that remains overloaded after traffic relief.",
              "Restarting can clear a stuck process or temporary resource exhaustion, but it causes disruption and must happen only after traffic has moved away.",
              "high", True,
              [_action("fail_over_device", target, destination="healthy_redundant_peer"), _action("restart_device", target, mode="controlled")],
              ["Redundant peer is healthy and has sufficient capacity.", "Configuration backup is current.", "Human approval and maintenance policy allow restart."],
              ["Device returns healthy.", "Routing converges.", "Service metrics remain within limits for 10 minutes."],
              ["Failover path degrades.", "Device does not return within approved timeout."],
              [_action("restore_traffic_distribution", target, previous_state="captured_before_execution")]),
    ]


def plans_for_link_failure(diagnosis: dict[str, Any]) -> list[RecoveryPlan]:
    target = _target(diagnosis)
    return [
        _plan(diagnosis, "a", "Reroute around the failed link", "Restore connectivity using a healthy alternate path.",
              "Routing around a damaged cable, optic, port, or virtual path removes the failing segment from service.",
              "medium", False,
              [_action("validate_alternate_path", target), _action("reroute_traffic", target, path="healthy_alternate_path")],
              ["Alternate path is healthy and has capacity.", "Digital Twin validates reachability and no routing loop."],
              ["Packet loss falls below 1%.", "Affected-service checks recover."],
              ["Alternate path becomes congested.", "Route convergence fails."],
              [_action("restore_previous_route", target)]),
        _plan(diagnosis, "b", "Disable the degraded link", "Prevent unstable or error-prone forwarding.",
              "A flapping link can repeatedly disrupt routing; disabling it forces traffic onto the stable path.",
              "medium", True,
              [_action("disable_interface", target, reason="confirmed_degraded_link")],
              ["A healthy alternate path is active.", "The exact interface has been confirmed as faulty.", "Human approval is recorded."],
              ["Routing converges onto the alternate path.", "Interface errors and packet loss stop increasing."],
              ["No alternate path remains.", "Unexpected service dependency loses connectivity."],
              [_action("enable_interface", target)]),
        _plan(diagnosis, "c", "Repair or replace the physical/virtual link", "Remove the underlying link fault.",
              "Replacing faulty optics, cables, ports, or virtual tunnel settings removes the source of transmission errors.",
              "high", True,
              [_action("create_hardware_or_provider_ticket", target), _action("replace_or_repair_link_component", target)],
              ["Fault location is confirmed from both link ends.", "A maintenance window and operator are available."],
              ["Interface remains up without errors.", "Bidirectional loss is near zero after restoration."],
              ["Replacement link is unstable.", "New component fails validation."],
              [_action("revert_link_component", target, previous_state="captured_before_maintenance")]),
    ]


def plans_for_network_congestion(diagnosis: dict[str, Any]) -> list[RecoveryPlan]:
    target = _target(diagnosis)
    return [
        _plan(diagnosis, "a", "Shift a bounded share of traffic", "Reduce utilization on the saturated path.",
              "Using an underutilized path lowers queueing delay and packet drops on the congested interface.",
              "medium", False,
              [_action("validate_backup_capacity", target, minimum_headroom_percent=30), _action("shift_traffic", target, maximum_percent=25, destination="underutilized_path")],
              ["An alternate path exists.", "Digital Twin predicts no overload on the alternate path."],
              ["Utilization falls below 80%.", "Latency and loss improve."],
              ["Alternate path utilization exceeds 85%."],
              [_action("restore_traffic_distribution", target, previous_state="captured_before_execution")]),
        _plan(diagnosis, "b", "Prioritize critical traffic", "Protect important applications during a capacity shortage.",
              "Quality-of-service rules give latency-sensitive or business-critical traffic priority over bulk transfers.",
              "medium", True,
              [_action("apply_qos_policy", target, priority_classes=["voice", "payments", "control_plane"], deprioritized_classes=["bulk", "best_effort"])],
              ["Traffic classes are correctly identified.", "Policy permits QoS modification.", "Digital Twin confirms no control-plane starvation."],
              ["Critical traffic latency and loss improve.", "Policy counters match expected classifications."],
              ["Critical traffic is classified incorrectly.", "Control-plane health degrades."],
              [_action("remove_qos_policy", target)]),
        _plan(diagnosis, "c", "Throttle or schedule bulk transfers", "Reduce non-urgent demand.",
              "Backups, replication, updates, and large file transfers can be delayed or limited so they no longer consume the shared bottleneck.",
              "low", False,
              [_action("identify_bulk_flows", target), _action("throttle_traffic_class", target, traffic_class="bulk", maximum_percent_of_link=20)],
              ["Bulk flows are identified.", "Critical services are excluded."],
              ["Link utilization and drop rate decrease.", "Bulk jobs remain resumable."],
              ["Critical application traffic is accidentally throttled."],
              [_action("remove_traffic_throttle", target, traffic_class="bulk")]),
        _plan(diagnosis, "d", "Increase path capacity", "Provide durable headroom for sustained demand.",
              "A larger link or an additional path addresses a recurring capacity mismatch rather than only treating the immediate symptoms.",
              "high", True,
              [_action("request_capacity_upgrade", target, target_utilization_percent=70), _action("provision_additional_path", target)],
              ["Capacity trend confirms recurrent, not one-time, congestion.", "Budget, provider, and change approvals are available."],
              ["Peak utilization remains below the target after the change."],
              ["New capacity is not provisioned correctly."],
              [_action("restore_previous_capacity_configuration", target)]),
    ]


def plans_for_memory_exhaustion(diagnosis: dict[str, Any]) -> list[RecoveryPlan]:
    target = _target(diagnosis)
    return [
        _plan(diagnosis, "a", "Reduce session or connection pressure", "Free memory without restarting the node.",
              "Excess sessions, route entries, or caches consume memory; safely reducing the source can restore headroom.",
              "medium", False,
              [_action("inspect_memory_consumers", target), _action("apply_connection_admission_limit", target, scope="non_critical_new_sessions")],
              ["Memory consumer is identified.", "Critical sessions are excluded.", "Digital Twin validates service capacity."],
              ["Available memory increases above 256 MB.", "New critical connections succeed."],
              ["Critical session creation fails."],
              [_action("remove_connection_admission_limit", target)]),
        _plan(diagnosis, "b", "Fail over and perform a controlled restart", "Clear temporary memory pressure or a suspected leak.",
              "A restart may restore memory, but only after a healthy peer takes traffic and an operator approves the disruption.",
              "high", True,
              [_action("fail_over_device", target, destination="healthy_redundant_peer"), _action("restart_device", target, mode="controlled")],
              ["Healthy redundant capacity exists.", "Configuration backup is current.", "Human approval is granted."],
              ["Available memory returns to normal.", "Node rejoins without service errors."],
              ["Node does not rejoin within timeout.", "Failover peer degrades."],
              [_action("restore_traffic_distribution", target, previous_state="captured_before_execution")]),
        _plan(diagnosis, "c", "Apply a software fix or scale memory", "Address recurring memory exhaustion.",
              "A memory leak or insufficient hardware requires a durable repair, such as a patched image or a larger instance.",
              "high", True,
              [_action("schedule_software_update", target, purpose="memory_leak_fix"), _action("scale_memory_capacity", target)],
              ["Root cause is confirmed by memory trend or vendor advisory.", "Change window and rollback image are available."],
              ["Memory remains stable through expected peak load."],
              ["New software version causes regression."],
              [_action("restore_previous_software_or_capacity", target)]),
    ]


def plans_for_node_or_interface_failure(diagnosis: dict[str, Any]) -> list[RecoveryPlan]:
    target = _target(diagnosis)
    return [
        _plan(diagnosis, "a", "Automatic failover to a healthy peer", "Restore service while the failed component is isolated.",
              "Redundant devices or paths can take over traffic without waiting for the failed component to recover.",
              "medium", False,
              [_action("validate_redundant_peer", target), _action("fail_over_device_or_path", target, destination="healthy_redundant_peer")],
              ["Peer/path is healthy and has capacity.", "Digital Twin verifies service reachability after failover."],
              ["Services recover and routing remains stable."],
              ["Redundant peer becomes unhealthy."],
              [_action("restore_previous_active_path", target)]),
        _plan(diagnosis, "b", "Recover the failed interface or node", "Return the component to service after validation.",
              "Re-enabling a known-good interface or controlled recovery of a node may resolve a transient fault, but must not destabilize active traffic.",
              "high", True,
              [_action("collect_diagnostics", target), _action("recover_node_or_interface", target, mode="controlled")],
              ["Failure cause is investigated.", "Traffic is safely on a redundant path.", "Human approval is granted."],
              ["Node/interface becomes healthy.", "No errors recur during observation window."],
              ["Recovered component flaps or introduces errors."],
              [_action("isolate_node_or_interface", target)]),
        _plan(diagnosis, "c", "Replace failed infrastructure", "Fix a confirmed persistent failure.",
              "Persistent hardware, virtual appliance, or provider failures require replacement or provider remediation.",
              "high", True,
              [_action("create_replacement_or_provider_ticket", target), _action("replace_failed_component", target)],
              ["Failure is persistent and component identity is confirmed.", "Maintenance approval is available."],
              ["Replacement passes health, reachability, and redundancy tests."],
              ["Replacement fails validation."],
              [_action("restore_previous_active_path", target)]),
    ]


def plans_for_routing_or_configuration_issue(diagnosis: dict[str, Any]) -> list[RecoveryPlan]:
    target = _target(diagnosis)
    return [
        _plan(diagnosis, "a", "Restore the last known-good configuration", "Undo the likely triggering configuration change.",
              "If degradation began after a route or policy change, restoring the prior validated configuration can re-establish the intended path.",
              "medium", False,
              [_action("capture_current_configuration", target), _action("restore_config_version", target, version="last_known_good")],
              ["A known-good version is available.", "The current configuration differs from that version.", "Digital Twin validates routes, reachability, and rollback."],
              ["Affected prefix is reachable.", "Route convergence completes.", "Service error rate improves."],
              ["A protected prefix becomes unreachable.", "A routing loop is detected."],
              [_action("restore_config_version", target, version="captured_before_execution")]),
        _plan(diagnosis, "b", "Apply a narrow route correction", "Repair only the incorrect route or policy entry.",
              "A targeted correction minimizes blast radius when the exact bad next hop, prefix, or policy rule is known.",
              "medium", True,
              [_action("validate_route_diff", target), _action("apply_route_policy_correction", target, scope="confirmed_incorrect_prefix_or_rule")],
              ["Incorrect prefix/rule and intended state are confirmed.", "Digital Twin shows no route loop or unintended prefix change."],
              ["Trace path reaches the intended destination.", "No unrelated route changes occur."],
              ["Unexpected prefixes change next hop.", "Routing adjacency becomes unstable."],
              [_action("restore_route_policy", target, version="captured_before_execution")]),
        _plan(diagnosis, "c", "Temporarily steer traffic through a healthy path", "Contain user impact while a permanent route repair is prepared.",
              "Temporary traffic steering restores service without immediately changing the suspected faulty policy.",
              "medium", False,
              [_action("validate_alternate_path", target), _action("steer_traffic", target, path="healthy_temporary_path", maximum_percent=25)],
              ["Healthy alternate path has capacity.", "Digital Twin confirms no loop and acceptable latency."],
              ["Affected service recovers.", "Alternate path stays under 80% utilization."],
              ["Alternate path congestion or error rate rises."],
              [_action("restore_previous_route", target)]),
    ]


PLAN_BUILDERS = {
    "network_device_overload": plans_for_network_device_overload,
    "link_failure": plans_for_link_failure,
    "network_congestion": plans_for_network_congestion,
    "memory_exhaustion": plans_for_memory_exhaustion,
    "node_or_interface_failure": plans_for_node_or_interface_failure,
    "routing_or_configuration_issue": plans_for_routing_or_configuration_issue,
}


def explain_recovery_plan(plan: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    """Create an evidence-grounded explanation for an operator or dashboard.

    This deterministic explanation is also the safe source material for an LLM
    rewrite. It makes no claim that a plan is approved for execution.
    """
    target = next((item for item in diagnosis.get("affected_targets", []) if item), "the affected network component")
    approval = (
        "It requires human approval before any execution."
        if plan["requires_human_approval"]
        else "It still requires Digital Twin validation and Safety Engine approval before execution."
    )
    explanation = (
        f"This plan is recommended for {target} because {plan['rationale']} "
        f"Its objective is to {plan['objective'].rstrip('.').lower()}. "
        f"A successful plan should verify: {' '.join(plan['verification'][:2])} {approval}"
    )
    return {
        "explanation": explanation,
        "llm_grounding_data": {
            "diagnosis": {
                "root_cause": diagnosis["root_cause"],
                "confidence": diagnosis["confidence"],
                "supporting_evidence": diagnosis["supporting_evidence"],
                "contradicting_evidence": diagnosis["contradicting_evidence"],
            },
            "plan": {
                "title": plan["title"],
                "objective": plan["objective"],
                "rationale": plan["rationale"],
                "risk": plan["risk"],
                "requires_human_approval": plan["requires_human_approval"],
                "preconditions": plan["preconditions"],
                "verification": plan["verification"],
                "stop_conditions": plan["stop_conditions"],
            },
            "instruction": (
                "Rewrite for clarity only. Do not add a cause, metric, action, "
                "guarantee, approval, or safety claim not contained in this data."
            ),
        },
    }


def generate_recovery_plans(
    diagnosis_report: dict[str, Any], max_diagnoses: int = 3
) -> dict[str, Any]:
    """Create 2-5 candidate recovery plans for each of the top diagnoses."""
    groups = []
    for hypothesis in diagnosis_report.get("hypotheses", [])[:max_diagnoses]:
        builder = PLAN_BUILDERS.get(hypothesis["root_cause"])
        if not builder:
            continue
        plans = builder(hypothesis)
        if not 2 <= len(plans) <= 5:
            raise ValueError("Each diagnosis must produce between 2 and 5 plans.")
        serialized_plans = []
        for plan in plans:
            serialized = asdict(plan)
            serialized.update(explain_recovery_plan(serialized, hypothesis))
            serialized_plans.append(serialized)
        groups.append({"diagnosis": hypothesis, "plans": serialized_plans})
    return {
        "incident_id": diagnosis_report.get("incident_id"),
        "planner_version": "1.0",
        "plan_groups": groups,
        "safety_note": (
            "These are candidate plans only. Validate every plan in the Digital Twin, "
            "then obtain a bounded Safety Engine approval before execution."
        ),
    }


if __name__ == "__main__":
    import json

    example_payload = {
        "incident": {"incident_id": "INC-1042"},
        "nodes": [{
            "node_id": "router-r3", "node_type": "router", "health": {"status": "degraded"},
            "telemetry": {
                "cpu": {"usage_percent": 97.0},
                "memory": {"usage_percent": 65.0, "available_mb": 1024},
                "network": {"latency_ms": {"average": 250.0}, "packet_loss_percent": {"value": 3.5}},
            },
            "interfaces": [{
                "interface_id": "router-r3:eth0", "admin_status": "up", "oper_status": "up",
                "utilization_percent": {"inbound": 96.0, "outbound": 72.0}, "drop_count": 540,
            }],
        }],
    }
    diagnosis_report = diagnose(example_payload)
    print(json.dumps(generate_recovery_plans(diagnosis_report), indent=2))
