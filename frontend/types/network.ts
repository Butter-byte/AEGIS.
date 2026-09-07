// Mirrors backend/models/enums.py.
export type NodeStatus = "healthy" | "degraded" | "failed" | "quarantined";

export type EdgeStatus = "active" | "congested" | "failed";

export type ServiceStatus = string;

export type NetworkNodeData = {
  label: string;
  status?: NodeStatus;
  cpu?: number;
  latency?: number;
};

export type NetworkNode = {
  id: string;
  status: NodeStatus;
  cpu_percent: number;
  latency_ms: number;
  packet_loss_percent: number;
  capacity: number;
  load: number;
};

export type NetworkEdge = {
  id: string;
  source: string;
  target: string;
  bandwidth_mbps: number;
  latency_ms: number;
  packet_loss_percent: number;
  utilization_percent: number;
  status: EdgeStatus;
};

export type ServiceState = {
  id: string;
  host_node: string;
  required_bandwidth: number;
  status: ServiceStatus;
  depends_on: string[];
};

export type NetworkState = {
  version: number;
  updated_at: string;
  nodes: Record<string, NetworkNode>;
  edges: NetworkEdge[];
  services: Record<string, ServiceState>;
  active_fault_ids: string[];
};

export type EventType =
  | "state"
  | "fault"
  | "diagnosis"
  | "simulation"
  | "safety"
  | "recovery"
  | "error";

export type WSEnvelope<T = unknown> = {
  type: EventType;
  seq: number;
  at: string;
  version: number | null; // backend WSEvent.version is int | None
  payload: T;
};

export type StatePayload = {
  state: NetworkState;
};

// --- GET /telemetry (backend TelemetryEngine.derive) ---

export type NodeTelemetry = {
  cpu: number; // percent 0–100
  latency: number; // ms
  packet_loss: number; // ratio 0.0–1.0
  status: string; // NodeStatus enum ("healthy" | "degraded" | "failed" | "quarantined")
};

export type Telemetry = {
  at: string; // ISO-8601 UTC
  based_on_version: number;
  network_availability: number; // ratio 0.0–1.0
  avg_latency: number; // ms
  max_latency: number; // ms
  total_packet_loss: number; // ratio 0.0–1.0
  active_nodes: number;
  failed_nodes: number;
  quarantined_nodes: number;
  congested_edges: number;
  failed_edges: number;
  per_node: Record<string, NodeTelemetry>;
};

// --- POST /recovery/run  (mirrors backend/models/{run,diagnosis,recovery,simulation,safety}.py) ---

export type RunOutcome =
  | "applied"
  | "approved_pending"
  | "no_safe_plan"
  | "no_plan"
  | "diagnosis_failed"
  | "error";

// Closed action vocabulary — backend/models/recovery.py. Discriminated on `type`.
export type RecoveryAction =
  | { type: "reroute"; service_id: string; avoid_nodes: string[]; avoid_edges: string[] }
  | { type: "drain_node"; node_id: string }
  | { type: "restore_node"; node_id: string }
  | { type: "migrate_service"; service_id: string; to_node: string }
  | { type: "quarantine_node"; node_id: string }
  | { type: "reset_link"; edge_id: string };

export type RecoveryPlan = {
  id: string;
  created_at: string;
  based_on_version: number;
  targets_diagnosis: string;
  strategy_label: string;
  rationale: string;
  actions: RecoveryAction[];
  source: "llm" | "heuristic";
};

export type SimMetrics = {
  availability: number; // 0.0–1.0
  avg_latency: number; // ms
  max_latency: number; // ms
  worst_node_load: number; // 0.0–1.0+ (max load/capacity)
  unreachable_services: string[];
  path_count: number; // distinct paths resolved network-wide — not per-service
};

export type SimDelta = {
  availability: number; // post minus pre
  avg_latency: number;
  max_latency: number;
};

export type SimulationResult = {
  plan_id: string;
  based_on_version: number;
  feasible: boolean;
  infeasible_reason: string | null;
  metrics: SimMetrics | null; // null iff infeasible
  delta: SimDelta | null;
  errors: string[];
  computed_at: string;
};

export type ViolationLevel = "warning" | "critical";

export type Violation = {
  rule: string;
  detail: string;
  level: ViolationLevel;
};

export type SafetyDecision = {
  plan_id: string;
  based_on_version: number;
  approved: boolean;
  violations: Violation[];
  evaluated: Record<string, number>;
  policy_version: string;
  decided_at: string;
};

export type RecoveryDiagnosis = {
  id: string;
  created_at: string;
  based_on_version: number;
  summary: string; // "<Label>: <targets>" — the closest thing to a root-cause label
  suspected_nodes: string[];
  suspected_edges: string[];
  suspected_services: string[];
  confidence: number; // 0.0–1.0
  rationale: string;
};

export type CandidateResult = {
  plan: RecoveryPlan;
  simulation: SimulationResult;
  safety: SafetyDecision;
};

export type RecoveryRunResult = {
  run_id: string;
  based_on_version: number;
  outcome: RunOutcome;
  message: string;
  diagnosis: RecoveryDiagnosis | null; // null only for outcome === "diagnosis_failed"
  candidates: CandidateResult[];
  applied_plan_id: string | null; // set only when the backend applied a plan
  resulting_version: number | null;
  completed_at: string;
};

// --- Recovery WebSocket payloads (backend/pipeline.py _emit calls) ---

export type RecoveryEventPayload = {
  run_id: string;
  stage: "started" | "completed";
  result: RecoveryRunResult | null;
};

export type DiagnosisEventPayload = { run_id: string; diagnosis: RecoveryDiagnosis };
export type SimulationEventPayload = { run_id: string; result: SimulationResult };
export type SafetyEventPayload = { run_id: string; decision: SafetyDecision };
export type ErrorEventPayload = { run_id: string; code: string; message: string };

// Live progress phase — cosmetic only; the HTTP RecoveryRunResult is authoritative.
export type RecoveryPhase =
  | "idle"
  | "diagnosing"
  | "simulating"
  | "evaluating"
  | "executing"
  | "done";