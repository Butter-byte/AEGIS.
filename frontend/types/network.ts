export type NodeStatus = "healthy" | "degraded" | "failed";

export type EdgeStatus = string;

export type ServiceStatus = string;

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