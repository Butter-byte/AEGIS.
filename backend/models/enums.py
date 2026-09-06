"""Canonical enums. Source of truth: docs/BACKEND_SCHEMA.md §1.2."""

from __future__ import annotations

from enum import Enum


class NodeStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    failed = "failed"
    quarantined = "quarantined"


class EdgeStatus(str, Enum):
    active = "active"
    congested = "congested"
    failed = "failed"


class ServiceStatus(str, Enum):
    running = "running"
    degraded = "degraded"
    down = "down"


class FaultType(str, Enum):
    kill_node = "kill_node"
    degrade_node = "degrade_node"
    overload_node = "overload_node"
    cut_edge = "cut_edge"
    congest_edge = "congest_edge"
    traffic_spike = "traffic_spike"


class ActionType(str, Enum):
    reroute = "reroute"
    drain_node = "drain_node"
    restore_node = "restore_node"
    migrate_service = "migrate_service"
    quarantine_node = "quarantine_node"
    reset_link = "reset_link"


class ViolationLevel(str, Enum):
    warning = "warning"
    critical = "critical"


class RunOutcome(str, Enum):
    applied = "applied"
    approved_pending = "approved_pending"
    no_safe_plan = "no_safe_plan"
    no_plan = "no_plan"
    diagnosis_failed = "diagnosis_failed"
    error = "error"


class WSEventType(str, Enum):
    state = "state"
    fault = "fault"
    diagnosis = "diagnosis"
    simulation = "simulation"
    safety = "safety"
    recovery = "recovery"
    error = "error"
