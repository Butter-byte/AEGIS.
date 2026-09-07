import { useState } from "react";
import type { Node } from "@xyflow/react";
import { runRecovery } from "../services/api";
import type { NetworkNodeData } from "../types/network";

type NodeInspectorProps = {
  node: Node<NetworkNodeData> | null;
  onIsolate: () => void;
  disabled?: boolean;
};

function NodeInspector({ node, onIsolate, disabled = false }: NodeInspectorProps) {
  const [isRecovering, setIsRecovering] = useState(false);

  if (!node) {
    return (
      <div className="node-inspector empty">
        <span>SELECT A NODE</span>
      </div>
    );
  }

  const data = node.data ?? {};
  const status = data.status ?? "healthy";

  const handleRecovery = async () => {
    setIsRecovering(true);

    try {
      await runRecovery();
    } catch (error) {
      console.error("Recovery request failed:", error);
    } finally {
      setIsRecovering(false);
    }
  };

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
        <button onClick={onIsolate} disabled={isRecovering || disabled}>
          ISOLATE NODE
        </button>

        <button onClick={handleRecovery} disabled={isRecovering || disabled}>
          {isRecovering ? "RECOVERING..." : "TRIGGER RECOVERY"}
        </button>
      </div>
    </div>
  );
}

export default NodeInspector;