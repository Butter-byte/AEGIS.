import type { Node } from "@xyflow/react";
import { runRecovery } from "../services/api";

type NetworkNodeData = {
  label: string;
  status?: "healthy" | "degraded" | "failed";
  cpu?: number;
  latency?: number;
};

type NodeInspectorProps = {
  node: Node | null;
  onIsolate: () => void;
};

function NodeInspector({ node, onIsolate }: NodeInspectorProps) {
  if (!node) {
    return (
      <div className="node-inspector empty">
        <span>SELECT A NODE</span>
      </div>
    );
  }

  const data = node.data as NetworkNodeData;

  return (
    <div className="node-inspector">
      <div className="inspector-header">
        <div>
          <span className="inspector-label">NODE</span>
          <h3>{data.label}</h3>
        </div>

        <span className={`inspector-status ${data.status ?? "healthy"}`}>
          {data.status?.toUpperCase() ?? "HEALTHY"}
        </span>
      </div>

      <div className="inspector-metrics">
        <div>
          <span>CPU UTILIZATION</span>
          <strong>{data.cpu ?? "--"}%</strong>
        </div>

        <div>
          <span>LATENCY</span>
          <strong>
            {data.latency !== undefined ? `${data.latency} ms` : "--"}
          </strong>
        </div>
      </div>

      <div className="inspector-actions">
        <button onClick={onIsolate}>
          ISOLATE NODE
        </button>

        <button
          onClick={async () => {
            try {
              await runRecovery();
            } catch (error) {
              console.error("Recovery request failed:", error);
            }
          }}
        >
          TRIGGER RECOVERY
        </button>
      </div>
    </div >
  );
}

export default NodeInspector;