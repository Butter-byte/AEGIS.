"""Declarative recovery-plan generation from approved operation templates."""

from __future__ import annotations

from .models import Hypothesis, RecoveryPlan


def action(operation: str, target: str, **parameters: object) -> dict[str, object]: return {"operation": operation, "target": target, "parameters": parameters}


CATALOG = {
    "network_device_overload": [("Shift bounded traffic", "Reduce device load", "Traffic shifts to an underutilized path, reducing CPU and queues.", "medium", False, "shift_traffic"), ("Throttle bulk traffic", "Preserve critical capacity", "Bulk traffic is limited so essential flows keep capacity.", "low", False, "apply_rate_limit"), ("Controlled failover and restart", "Recover a persistently overloaded device", "Failover protects users before a restart clears temporary resource pressure.", "high", True, "restart_device")],
    "link_failure": [("Reroute around failed link", "Restore reachability", "A healthy alternate path bypasses the failing segment.", "medium", False, "reroute_traffic"), ("Disable confirmed bad interface", "Stop flapping", "A disabled faulty link cannot repeatedly disrupt forwarding.", "medium", True, "disable_interface"), ("Repair component", "Remove root fault", "Repairing a cable, optic, port, or tunnel resolves persistent errors.", "high", True, "repair_link")],
    "network_congestion": [("Shift bounded traffic", "Lower utilization", "Traffic moves to spare capacity, reducing queues and drops.", "medium", False, "shift_traffic"), ("Prioritize critical traffic", "Protect essential services", "QoS reserves capacity for critical flows.", "medium", True, "apply_qos_policy"), ("Throttle bulk transfers", "Reduce non-urgent demand", "Backups and bulk transfers release bottleneck capacity.", "low", False, "apply_rate_limit")],
    "memory_exhaustion": [("Limit non-critical sessions", "Free memory", "Admission limits reduce memory consumed by new non-critical sessions.", "medium", False, "apply_connection_admission_limit"), ("Fail over and restart", "Clear memory pressure", "A healthy peer protects service while restart clears temporary pressure.", "high", True, "restart_device"), ("Patch or scale capacity", "Fix recurrence", "A software update or more memory treats a leak or capacity gap.", "high", True, "scale_memory_capacity")],
    "node_or_interface_failure": [("Fail over to healthy peer", "Restore service", "Redundancy bypasses the unavailable node or interface.", "medium", False, "fail_over_device_or_path"), ("Controlled recovery", "Restore component", "Recovery is attempted only after traffic is protected.", "high", True, "recover_node_or_interface"), ("Replace component", "Fix persistent failure", "Replacement resolves confirmed hardware or provider failure.", "high", True, "replace_failed_component")],
    "routing_or_configuration_issue": [("Restore known-good configuration", "Undo likely bad change", "Restoring a validated configuration returns intended routing policy.", "medium", False, "restore_config_version"), ("Narrow route correction", "Fix confirmed bad prefix", "A limited correction minimizes blast radius.", "medium", True, "apply_route_policy_correction"), ("Temporary traffic steering", "Contain impact", "A healthy temporary path restores service while permanent repair is tested.", "medium", False, "steer_traffic")]
}


class RecoveryPlanner:
    def generate(self, hypothesis: Hypothesis) -> list[RecoveryPlan]:
        target = hypothesis.affected_targets[0]; plans = []
        for index, (title, objective, rationale, risk, approval, operation) in enumerate(CATALOG.get(hypothesis.root_cause, [])[:5], 1):
            plans.append(RecoveryPlan(f"{hypothesis.diagnosis_id}:plan-{index}", hypothesis.diagnosis_id, title, objective, rationale, risk, approval, [action(operation, target)], ["Digital Twin validation passes.", "Target remains in the approved scope."], ["Affected service health improves.", "No stop condition is met."], ["Packet loss or service errors worsen.", "A dependent service becomes unhealthy."], [action("restore_previous_state", target)]))
        return plans
