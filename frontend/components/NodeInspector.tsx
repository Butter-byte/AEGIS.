import type { Node } from "@xyflow/react";
import type { NetworkNodeData } from "../types/network";

type NodeInspectorProps = {
  node: Node<NetworkNodeData> | null;
  onIsolate: () => void;
  onTriggerRecovery: () => void;
  recoveryRunning: boolean;
  disabled?: boolean;
};

function NodeInspector({
  node,
  onIsolate,
  onTriggerRecovery,
  recoveryRunning,
  disabled = false,
}: NodeInspectorProps) {
  if (!node) {
    return (
      <div className="node-inspector empty">
        <span>SELECT A NODE</span>
      </div>
    );
  }

  const data = node.data;
  const status = data.status ?? "healthy";
  const busy = disabled || recoveryRunning;

  return (
    <div className="node-inspector">
      <div className="inspector-header">
        <div>
          <span className="inspector-label">NODE</span>
          <h3>{data.label ?? "Unknown Node"}</h3>
        </div>

        <span className={`inspector-status ${status}`}>
          {status.toUpperCase()}
        </span>
      </div>

      <div className="inspector-metrics">
        <div>
          <span>CPU UTILIZATION</span>
          <strong>
            {data.cpu !== undefined ? `${Math.round(data.cpu)}%` : "--"}
          </strong>
        </div>

        <div>
          <span>LATENCY</span>
          <strong>
            {data.latency !== undefined ? `${Math.round(data.latency)} ms` : "--"}
          </strong>
        </div>

        <div>
          <span>CAPACITY</span>
          <strong>
            {data.capacity !== undefined ? `${Math.round(data.capacity)} units` : "--"}
          </strong>
        </div>

        <div>
          <span>ACTIVE LOAD</span>
          <strong>
            {data.load !== undefined
              ? `${Math.round(data.load)} units`
              : "--"}
          </strong>
        </div>
      </div>

      {data.load !== undefined && data.capacity !== undefined && (
        <div className="inspector-resource-section">
          <div className="inspector-resource-header">
            <span>LOAD UTILIZATION</span>
            <strong>{Math.round((data.load / data.capacity) * 100)}%</strong>
          </div>
          <div className="inspector-resource-track">
            <div
              className={`inspector-resource-fill ${
                data.load / data.capacity > 0.85
                  ? "fill-high"
                  : data.load / data.capacity > 0.65
                  ? "fill-mid"
                  : "fill-low"
              }`}
              style={{
                width: `${Math.min(100, Math.round((data.load / data.capacity) * 100))}%`,
              }}
            />
          </div>
        </div>
      )}

      <div className="inspector-actions">
        <button onClick={onIsolate} disabled={busy}>
          ISOLATE NODE
        </button>

        <button onClick={onTriggerRecovery} disabled={busy}>
          {recoveryRunning ? "RECOVERING…" : "TRIGGER RECOVERY"}
        </button>
      </div>
    </div>
  );
}

export default NodeInspector;
