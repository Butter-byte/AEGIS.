import { useEffect, useRef, useState } from "react";
import type { NetworkState, StatePayload, Telemetry } from "../types/network";
import { connectSocket } from "../services/socket";
import { getTelemetry, injectFault } from "../services/api";
import type { FaultType } from "../services/api";
import NetworkGraph from "../components/NetworkGraph";
import EventLog from "../components/EventLog";
import { ReactFlowProvider } from "@xyflow/react";

// Fault controls in the panel. Every entry is a fault type the backend
// FaultInjector actually supports (see backend/models/enums.py::FaultType).
// `on: "node"` faults target the selected node; `on: "edge"` target the selected edge.
const FAULT_CONTROLS: { label: string; type: FaultType; on: "node" | "edge" }[] = [
  { label: "Kill Node", type: "kill_node", on: "node" },
  { label: "Overload Node", type: "overload_node", on: "node" },
  { label: "Traffic Spike", type: "traffic_spike", on: "node" },
  { label: "Break Link", type: "cut_edge", on: "edge" },
];

function averageCpu(telemetry: Telemetry): number {
  const nodes = Object.values(telemetry.per_node);
  if (nodes.length === 0) return 0;
  return Math.round(nodes.reduce((sum, node) => sum + node.cpu, 0) / nodes.length);
}

function formatWebSocketEvent(message: any): string {
  const payload = message.payload ?? {};

  switch (message.type) {
    case "fault":
      return `Fault injected: ${payload.fault?.target ?? "unknown target"
        }`;

    case "recovery":
      if (payload.stage === "started") {
        return `Recovery started`;
      }

      if (payload.stage === "completed") {
        return `Recovery completed`;
      }

      return `Recovery: ${payload.stage ?? "event"}`;

    case "diagnosis":
      return "Diagnosis completed";

    case "simulation":
      return "Recovery simulation evaluated";

    case "safety":
      return "Safety decision evaluated";

    case "error":
      return `System error: ${payload.message ?? "unknown error"
        }`;

    default:
      return `System event: ${message.type}`;
  }
}

function Dashboard() {
  const [networkState, setNetworkState] = useState<NetworkState | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [telemetryError, setTelemetryError] = useState(false);
  const [events, setEvents] = useState<string[]>([
    "Network initialized",
    "All systems operational",
  ]);

  // Fault-injection UI state. `selected*` are the click-selected topology
  // targets; `faultInFlight` is the type currently being POSTed (blocks
  // concurrent requests); `faultMessage` is panel-local feedback only — it is
  // never written to the Event Log, which stays purely WebSocket-driven.
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [faultInFlight, setFaultInFlight] = useState<FaultType | null>(null);
  const [faultMessage, setFaultMessage] =
    useState<{ kind: "info" | "error"; text: string } | null>(null);
  // Synchronous guard so a rapid double-click can't fire two POSTs before the
  // `faultInFlight` state re-render disables the buttons.
  const faultLock = useRef(false);

  // Telemetry is a pure projection of NetworkState, so re-fetch it whenever the
  // backend commits a new state version (fault / recovery / reset). The version
  // comes from the existing WebSocket `state` stream — no polling loop needed.
  useEffect(() => {
    let cancelled = false;

    getTelemetry()
      .then((data) => {
        if (cancelled) return;
        setTelemetry(data);
        setTelemetryError(false);
      })
      .catch(() => {
        if (cancelled) return;
        setTelemetryError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [networkState?.version]);

  useEffect(() => {
    const connection = connectSocket({
      onOpen: () => {
        console.log("AEGIS WebSocket connected");
      },

      onMessage: (message) => {
        console.log("AEGIS WS MESSAGE:", message);

        if (message.type === "state") {
          const payload = message.payload as StatePayload;
          setNetworkState(payload.state);
          return;
        }

        const event = formatWebSocketEvent(message);

        setEvents((currentEvents) => [
          event,
          ...currentEvents,
        ]);
      },

      onClose: () => {
        console.log("AEGIS WebSocket disconnected");
      },

      onError: (error) => {
        console.error("AEGIS WebSocket error:", error);
      },
    });

    return connection.close;
  }, []);

  const runFault = async (type: FaultType, on: "node" | "edge") => {
    if (faultLock.current) return; // one fault request at a time

    const target = on === "node" ? selectedNodeId : selectedEdgeId;
    if (!target) {
      setFaultMessage({
        kind: "error",
        text: on === "node" ? "Select a node first." : "Select a link first.",
      });
      return;
    }

    faultLock.current = true;
    setFaultInFlight(type);
    setFaultMessage(null);
    try {
      await injectFault(type, target);
      // Success is only claimed after the backend 2xx response. The topology /
      // telemetry update themselves from the backend's WebSocket state frame.
      setFaultMessage({ kind: "info", text: `${type} accepted on ${target}` });
    } catch (error) {
      setFaultMessage({
        kind: "error",
        text: `${type} failed: ${error instanceof Error ? error.message : "request error"}`,
      });
    } finally {
      faultLock.current = false;
      setFaultInFlight(null);
    }
  };

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="topbar">
        <div>
          <h1>AEGIS</h1>
          <span>Autonomous Network Recovery System</span>
        </div>

        <div className="system-status">
          <span className="status-dot" />
          SYSTEM OPERATIONAL
        </div>
      </header>

      {/* Main dashboard */}
      <main className="dashboard-grid">
        <section className="panel network-panel">
          <div className="panel-header">
            <h2>Network Topology</h2>
            <span>LIVE</span>
          </div>

          <div className="network-graph">
            <ReactFlowProvider>
              <NetworkGraph
                networkState={networkState}
                selectedNodeId={selectedNodeId}
                selectedEdgeId={selectedEdgeId}
                onSelectNode={(id) => {
                  setSelectedNodeId(id);
                  setSelectedEdgeId(null);
                }}
                onSelectEdge={(id) => {
                  setSelectedEdgeId(id);
                  setSelectedNodeId(null);
                }}
                onIsolateSelected={() => runFault("kill_node", "node")}
                actionPending={faultInFlight !== null}
              />
            </ReactFlowProvider>
          </div>
        </section>

        <section className="panel telemetry-panel">
          <div className="panel-header">
            <h2>System Telemetry</h2>
            {telemetryError ? (
              <span className="error">UNAVAILABLE</span>
            ) : (
              <span>{telemetry ? "LIVE" : "SYNC…"}</span>
            )}
          </div>

          <div className="telemetry-grid">
            {(
              [
                ["CPU", telemetry ? `${averageCpu(telemetry)}%` : null],
                ["LATENCY", telemetry ? `${Math.round(telemetry.avg_latency)} ms` : null],
                [
                  "PACKET LOSS",
                  telemetry ? `${(telemetry.total_packet_loss * 100).toFixed(1)}%` : null,
                ],
                ["ACTIVE NODES", telemetry ? `${telemetry.active_nodes}` : null],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{telemetryError ? "—" : value ?? "…"}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="panel fault-panel">
          <div className="panel-header">
            <h2>Fault Injection</h2>
            <span>
              {selectedNodeId
                ? `NODE ${selectedNodeId}`
                : selectedEdgeId
                  ? `LINK ${selectedEdgeId}`
                  : "NO TARGET"}
            </span>
          </div>

          <div className="fault-buttons">
            {FAULT_CONTROLS.map(({ label, type, on }) => {
              const hasTarget = on === "node" ? !!selectedNodeId : !!selectedEdgeId;
              const busy = faultInFlight === type;
              return (
                <button
                  key={type}
                  onClick={() => runFault(type, on)}
                  disabled={!hasTarget || faultInFlight !== null}
                >
                  {busy ? `${label}…` : label}
                </button>
              );
            })}
          </div>

          {faultMessage && (
            <p className={`fault-status ${faultMessage.kind}`}>{faultMessage.text}</p>
          )}
          <p className="fault-hint">
            Click a node or link in the topology to choose a target.
          </p>
        </section>

        <section className="panel event-panel">
          <div className="panel-header">
            <h2>Event Log</h2>
          </div>

          <EventLog events={events} />
        </section>
      </main>
    </div>
  );
}

export default Dashboard;