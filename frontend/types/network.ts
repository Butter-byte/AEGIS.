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
  version: number;
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