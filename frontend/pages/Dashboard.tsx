import { useState } from "react";
import { useEffect } from "react";
import { connectSocket } from "../services/socket";
import NetworkGraph from "../components/NetworkGraph";
import EventLog from "../components/EventLog";

function Dashboard() {
  useEffect(() => {
    const connection = connectSocket({
      onOpen: () => {
        console.log("AEGIS WebSocket connected");
      },

      onMessage: (message) => {
        console.log("AEGIS WebSocket message:", message);
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
            <NetworkGraph onEvent={addEvent} />
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