"""Canonical shared contracts — the integration boundary between all four owners.

LEAF package (Vikash-owned): imports nothing else from `backend/`. Source of
truth: docs/BACKEND_SCHEMA.md. No module outside this package may define a
canonical cross-module type.
"""

from __future__ import annotations

from .common import (
    DIAGNOSIS_ID,
    EDGE_ID,
    FAULT_ID,
    NODE_ID,
    PLAN_ID,
    RUN_ID,
    SERVICE_ID,
    SIM_ID,
    StrictModel,
    UtcDatetime,
    edge_id_for,
    new_diagnosis_id,
    new_fault_id,
    new_plan_id,
    new_run_id,
    new_sim_id,
    utcnow,
)
from .diagnosis import Diagnosis
from .enums import (
    ActionType,
    EdgeStatus,
    FaultType,
    NodeStatus,
    RunOutcome,
    ServiceStatus,
    ViolationLevel,
    WSEventType,
)
from .errors import (
    AegisError,
    Conflict,
    ErrorBody,
    ErrorEnvelope,
    ExecutionFailed,
    InternalError,
    InvalidFault,
    InvalidTarget,
    ModuleNotWired,
    NotFound,
    PipelineError,
    RequestValidationFailed,
)
from .events import WSEvent
from .execution import ExecutionResult
from .faults import Fault, FaultRequest
from .recovery import (
    DrainNodeAction,
    MigrateServiceAction,
    QuarantineNodeAction,
    RecoveryAction,
    RecoveryPlan,
    RerouteAction,
    ResetLinkAction,
    RestoreNodeAction,
)
from .run import CandidateResult, PlanRequest, RecoveryRunResult, RunRequest
from .safety import PolicyConfig, SafetyDecision, Violation
from .state import EdgeState, NetworkState, NodeState, ServiceState
from .telemetry import NodeTelemetry, Telemetry
from .twin import SimDelta, SimMetrics, SimulationResult
from .validation import SchemaError, parse_diagnosis, parse_plan

__all__ = [
    # common
    "StrictModel", "UtcDatetime", "utcnow", "edge_id_for",
    "NODE_ID", "EDGE_ID", "SERVICE_ID", "FAULT_ID", "DIAGNOSIS_ID", "PLAN_ID", "SIM_ID", "RUN_ID",
    "new_fault_id", "new_diagnosis_id", "new_plan_id", "new_sim_id", "new_run_id",
    # enums
    "NodeStatus", "EdgeStatus", "ServiceStatus", "FaultType", "ActionType",
    "ViolationLevel", "RunOutcome", "WSEventType",
    # state
    "NetworkState", "NodeState", "EdgeState", "ServiceState",
    # telemetry
    "Telemetry", "NodeTelemetry",
    # faults
    "Fault", "FaultRequest",
    # diagnosis
    "Diagnosis",
    # recovery
    "RecoveryAction", "RecoveryPlan", "RerouteAction", "DrainNodeAction",
    "RestoreNodeAction", "MigrateServiceAction", "QuarantineNodeAction", "ResetLinkAction",
    # twin
    "SimulationResult", "SimMetrics", "SimDelta",
    # safety
    "SafetyDecision", "Violation", "PolicyConfig",
    # execution
    "ExecutionResult",
    # run
    "RecoveryRunResult", "CandidateResult", "RunRequest", "PlanRequest",
    # errors
    "AegisError", "ErrorBody", "ErrorEnvelope", "RequestValidationFailed",
    "InvalidFault", "InvalidTarget", "NotFound", "Conflict", "PipelineError",
    "ExecutionFailed", "InternalError", "ModuleNotWired",
    # events
    "WSEvent",
    # validation
    "parse_diagnosis", "parse_plan", "SchemaError",
]
