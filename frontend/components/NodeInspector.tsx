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
            {data.cpu !== undefined ? `${data.cpu}%` : "--"}
          </strong>
        </div>

        <div>
          <span>LATENCY</span>
          <strong>
            {data.latency !== undefined ? `${data.latency} ms` : "--"}
          </strong>
        </div>
      </div>

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
