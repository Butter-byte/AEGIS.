import { useEffect, useRef, useState } from "react";
import type {
  DiagnosisEventPayload,
  ErrorEventPayload,
  NetworkState,
  RecoveryEventPayload,
  RecoveryPhase,
  RecoveryRunResult,
  SafetyEventPayload,
  SimulationEventPayload,
  StatePayload,
  Telemetry,
  WSEnvelope,
} from "../types/network";
import { connectSocket } from "../services/socket";
import { getNetworkState, getTelemetry, injectFault, resetNetwork, runRecovery } from "../services/api";
import type { FaultType } from "../services/api";
import NetworkGraph from "../components/NetworkGraph";
import RecoveryPanel from "../components/RecoveryPanel";
import PipelineBar from "../components/PipelineBar";
import EventLog from "../components/EventLog";
import type { LogEntry } from "../components/EventLog";
import { ReactFlowProvider } from "@xyflow/react";

const TOPOLOGY_LEGEND: { cls: string; label: string }[] = [
  { cls: "lg-healthy", label: "Healthy" },
  { cls: "lg-degraded", label: "Degraded" },
  { cls: "lg-failed", label: "Failed" },
  { cls: "lg-quarantined", label: "Quarantined" },
  { cls: "lg-congested", label: "Congested link" },
  { cls: "lg-failed-link", label: "Failed link" },
];

const MAX_EVENTS = 100;

// Fault controls in the panel. Every entry is a fault type the backend
// FaultInjector actually supports (see backend/models/enums.py::FaultType).
// `on: "node"` faults target the selected node; `on: "edge"` target the selected edge.
const FAULT_CONTROLS: { label: string; type: FaultType; on: "node" | "edge" }[] = [
  { label: "Kill Node", type: "kill_node", on: "node" },
  { label: "Overload Node", type: "overload_node", on: "node" },
  { label: "Traffic Spike", type: "traffic_spike", on: "node" },
  { label: "Break Link", type: "cut_edge", on: "edge" },
  { label: "Congest Link", type: "congest_edge", on: "edge" },
];

function averageCpu(telemetry: Telemetry): number {
  const nodes = Object.values(telemetry.per_node);
  if (nodes.length === 0) return 0;
  return Math.round(nodes.reduce((sum, node) => sum + node.cpu, 0) / nodes.length);
}

// Turn a real backend WS event into a timeline entry. Every field is read from
// the actual payload — nothing is fabricated. `state` frames are handled
// separately (topology / telemetry) and are not logged.
function formatWebSocketEvent(message: WSEnvelope): LogEntry | null {
  switch (message.type) {
    case "recovery": {
      const p = message.payload as RecoveryEventPayload;
      if (p.stage === "started") return { text: "Recovery started", kind: "info" };
      if (p.stage === "completed") {
        const outcome = p.result?.outcome ?? "completed";
        const bad = outcome === "no_safe_plan" || outcome === "error" || outcome === "diagnosis_failed";
        return { text: `Recovery complete — ${outcome}`, kind: bad ? "bad" : outcome === "applied" ? "ok" : "info" };
      }
      return null;
    }
    case "diagnosis": {
      const p = message.payload as DiagnosisEventPayload;
      return {
        text: `Diagnosis — ${p.diagnosis.summary} (${Math.round(p.diagnosis.confidence * 100)}%)`,
        kind: "info",
      };
    }
    case "simulation": {
      const p = message.payload as SimulationEventPayload;
      return {
        text: `Digital Twin — ${p.result.plan_id} ${p.result.feasible ? "feasible" : "infeasible"}`,
        kind: p.result.feasible ? "info" : "bad",
      };
    }
    case "safety": {
      const p = message.payload as SafetyEventPayload;
      return {
        text: `Safety Gate — ${p.decision.plan_id} ${p.decision.approved ? "APPROVED" : "REJECTED"}`,
        kind: p.decision.approved ? "ok" : "bad",
      };
    }
    case "error": {
      const p = message.payload as ErrorEventPayload;
      return { text: `System error — ${p.message ?? "unknown error"}`, kind: "bad" };
    }
    default:
      return { text: `System event — ${message.type}`, kind: "info" };
  }
}

const PHASE_ON_EVENT: Partial<Record<WSEnvelope["type"], RecoveryPhase>> = {
  diagnosis: "simulating",
  simulation: "simulating",
  safety: "evaluating",
};

const RESET_LOG: LogEntry[] = [{ text: "NETWORK RESET", kind: "boundary" }];

function Dashboard() {
  const [networkState, setNetworkState] = useState<NetworkState | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [telemetryError, setTelemetryError] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [events, setEvents] = useState<LogEntry[]>([
    { text: "Dashboard connected", kind: "info" },
  ]);

  const logEvent = (entry: LogEntry) =>
    setEvents((current) => [entry, ...current].slice(0, MAX_EVENTS));

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

  // Recovery UX state. The HTTP RecoveryRunResult is authoritative; `recoveryPhase`
  // is a cosmetic live indicator driven by real WS events. `recoveryView` toggles
  // the sidebar between NodeInspector and RecoveryPanel.
  const [recoveryResult, setRecoveryResult] = useState<RecoveryRunResult | null>(null);
  const [recoveryRunning, setRecoveryRunning] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const [recoveryPhase, setRecoveryPhase] = useState<RecoveryPhase>("idle");
  const [recoveryView, setRecoveryView] = useState(false);
  const recoveryLock = useRef(false);
  const recoveryRunningRef = useRef(false);
  // Mirrors recoveryResult for the (deps: []) socket handler, so it can tell
  // when a `state` frame belongs to a run other than the one on screen.
  const recoveryResultRef = useRef<RecoveryRunResult | null>(null);

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
        setWsConnected(true);
      },

      onMessage: (message) => {
        if (message.type === "state") {
          const next = (message.payload as StatePayload).state;
          setNetworkState(next);
          if (recoveryRunningRef.current) {
            setRecoveryPhase("executing");
          } else {
            // A committed mutation (reset / new fault / backend restart) that is
            // not part of the run currently on screen — dismiss the stale panel.
            const shown = recoveryResultRef.current;
            if (
              shown &&
              next.version !== shown.based_on_version &&
              next.version !== shown.resulting_version
            ) {
              setRecoveryView(false);
            }
          }
          return;
        }

        // Cosmetic live progress only — never a source of truth for the result.
        if (recoveryRunningRef.current) {
          if (message.type === "recovery") {
            const p = message.payload as RecoveryEventPayload;
            if (p.stage === "started") setRecoveryPhase("diagnosing");
          } else {
            const next = PHASE_ON_EVENT[message.type];
            if (next) setRecoveryPhase(next);
          }
        }

        const entry = formatWebSocketEvent(message);
        if (entry) setEvents((current) => [entry, ...current].slice(0, MAX_EVENTS));
      },

      onClose: () => {
        setWsConnected(false);
      },

      onError: () => {
        setWsConnected(false);
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
      logEvent({ text: `Fault injected — ${type} on ${target}`, kind: "fault" });
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

  const handleTriggerRecovery = async () => {
    if (recoveryLock.current) return; // one recovery run at a time

    recoveryLock.current = true;
    recoveryRunningRef.current = true;
    setRecoveryRunning(true);
    setRecoveryError(null);
    setRecoveryResult(null);
    recoveryResultRef.current = null;
    setRecoveryPhase("diagnosing");
    setRecoveryView(true);
    logEvent({ text: "RUN RECOVERY", kind: "boundary" });

    try {
      const result = await runRecovery();
      // The HTTP response is authoritative — the stepper/phase are discarded here.
      setRecoveryResult(result);
      recoveryResultRef.current = result;
      setRecoveryPhase("done");

      // Step 9 resync: only a backend "applied" outcome means state changed. The
      // WS `state` frame usually already updated it; refetch as a safe fallback.
      if (result.outcome === "applied") {
        try {
          setNetworkState(await getNetworkState());
        } catch {
          /* WS state stream will catch up */
        }
      }
    } catch (error) {
      setRecoveryError(error instanceof Error ? error.message : "Recovery request failed");
      setRecoveryPhase("idle");
    } finally {
      recoveryLock.current = false;
      recoveryRunningRef.current = false;
      setRecoveryRunning(false);
    }
  };

  const handleResetNetwork = async () => {
    if (recoveryRunning || faultInFlight !== null) return;
    // Clear recovery UI immediately; the topology/telemetry update themselves
    // from the backend's WebSocket `state` frame — never fabricated here.
    setRecoveryView(false);
    setRecoveryResult(null);
    recoveryResultRef.current = null;
    setRecoveryError(null);
    setRecoveryPhase("idle");
    setFaultMessage(null);
    setEvents(RESET_LOG);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    try {
      await resetNetwork();
    } catch (error) {
      setFaultMessage({
        kind: "error",
        text: `reset failed: ${error instanceof Error ? error.message : "request error"}`,
      });
    }
  };

  const showRecoveryPanel =
    recoveryView && (recoveryRunning || recoveryResult !== null || recoveryError !== null);

  // Operational status — derived from real connection / recovery state only.
  const status = !wsConnected
    ? { cls: "status-down", text: "BACKEND DISCONNECTED" }
    : recoveryRunning
      ? { cls: "status-busy", text: "RECOVERY IN PROGRESS" }
      : { cls: "status-ok", text: "SYSTEM OPERATIONAL" };

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="topbar">
        <div>
          <h1>AEGIS</h1>
          <span>Autonomous Network Recovery System</span>
        </div>

        <div className="topbar-right">
          <div className={`system-status ${status.cls}`}>
            <span className="status-dot" />
            {status.text}
          </div>
          <button
            className="reset-network"
            onClick={handleResetNetwork}
            disabled={recoveryRunning || faultInFlight !== null}
          >
            RESET NETWORK
          </button>
        </div>
      </header>

      {/* AEGIS recovery pipeline — the loop, always visible */}
      <PipelineBar
        phase={recoveryPhase}
        result={recoveryResult}
        running={recoveryRunning}
        error={recoveryError}
      />

      {/* Main dashboard */}
      <main className="dashboard-grid">
        <section className="panel network-panel">
          <div className="panel-header">
            <h2>Network Topology</h2>
            <span>LIVE</span>
          </div>

          <div className="legend">
            {TOPOLOGY_LEGEND.map(({ cls, label }) => (
              <span key={cls} className={`lg ${cls}`}>
                {label}
              </span>
            ))}
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
                onTriggerRecovery={handleTriggerRecovery}
                recoveryRunning={recoveryRunning}
                actionPending={faultInFlight !== null}
                sidebar={
                  showRecoveryPanel ? (
                    <RecoveryPanel
                      result={recoveryResult}
                      phase={recoveryPhase}
                      running={recoveryRunning}
                      error={recoveryError}
                      onClose={() => setRecoveryView(false)}
                    />
                  ) : undefined
                }
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
                [
                  "AVAILABILITY",
                  telemetry ? `${Math.round(telemetry.network_availability * 100)}%` : null,
                ],
                ["ACTIVE NODES", telemetry ? `${telemetry.active_nodes}` : null],
                [
                  "LINK FAULTS",
                  telemetry ? `${telemetry.failed_edges + telemetry.congested_edges}` : null,
                ],
                ["CPU", telemetry ? `${averageCpu(telemetry)}%` : null],
                ["LATENCY", telemetry ? `${Math.round(telemetry.avg_latency)} ms` : null],
                [
                  "PACKET LOSS",
                  telemetry ? `${(telemetry.total_packet_loss * 100).toFixed(1)}%` : null,
                ],
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

          <button
            className="run-recovery"
            onClick={handleTriggerRecovery}
            disabled={recoveryRunning}
          >
            {recoveryRunning ? "RUNNING RECOVERY…" : "RUN RECOVERY"}
          </button>
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