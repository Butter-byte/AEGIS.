import { useEffect, useState } from "react";
import type { NetworkState, StatePayload } from "../types/network";
import { connectSocket } from "../services/socket";
import NetworkGraph from "../components/NetworkGraph";
import EventLog from "../components/EventLog";

function formatWebSocketEvent(message: any): string {
  const payload = message.payload;

  switch (message.type) {
    case "fault":
      return `Fault: ${payload.action ?? "event"} — ${payload.fault?.type ?? "unknown"
        } on ${payload.fault?.target ?? "unknown"}`;

    case "diagnosis":
      return `Diagnosis: ${payload.diagnosis?.summary ?? "Recovery diagnosis completed"}`;

    case "simulation":
      return payload.result?.feasible
        ? `Simulation: recovery plan ${payload.result.plan_id} is feasible`
        : `Simulation: recovery plan is infeasible`;

    case "safety":
      return payload.decision?.approved
        ? `Safety: recovery plan ${payload.decision.plan_id} approved`
        : `Safety: recovery plan ${payload.decision?.plan_id ?? "unknown"} rejected`;

    case "recovery":
      if (payload.stage === "started") {
        return "Recovery pipeline started";
      }

      if (payload.stage === "completed") {
        return `Recovery completed: ${payload.result?.outcome ?? "finished"}`;
      }

      return "Recovery event received";

    case "error":
      return `Error: ${payload.message ?? "Recovery pipeline error"}`;

    default:
      return `AEGIS ${message.type.toUpperCase()} event received`;
  }
}

function Dashboard() {
  const [networkState, setNetworkState] = useState<NetworkState | null>(null);
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
  const [events, setEvents] = useState<string[]>([
    "Network initialized",
    "All systems operational",
  ]);

  const addEvent = (event: string) => {
    setEvents((currentEvents) => [event, ...currentEvents]);
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
            <NetworkGraph networkState={networkState} onEvent={addEvent} />
          </div>
        </section>

        <section className="panel telemetry-panel">
          <div className="panel-header">
            <h2>System Telemetry</h2>
          </div>

          <div className="telemetry-grid">
            <div>
              <span>CPU</span>
              <strong>42%</strong>
            </div>

            <div>
              <span>LATENCY</span>
              <strong>18 ms</strong>
            </div>

            <div>
              <span>PACKET LOSS</span>
              <strong>0.4%</strong>
            </div>

            <div>
              <span>ACTIVE NODES</span>
              <strong>12</strong>
            </div>
          </div>
        </section>

        <section className="panel fault-panel">
          <div className="panel-header">
            <h2>Fault Injection</h2>
          </div>

          <div className="fault-buttons">
            <button>Kill Node</button>
            <button>Break Link</button>
            <button>Traffic Spike</button>
            <button>Overload Node</button>
          </div>
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