import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { NetworkNodeData } from "../types/network";

function NetworkNode({ data }: NodeProps) {
  const nodeData = data as NetworkNodeData;

  const status = nodeData.status ?? "healthy";

  return (
    <div className={`network-node ${status}`}>
      <Handle type="target" position={Position.Top} />

      <div className="node-header">
        <div className="node-name">
          <span className="node-status" />
          {nodeData.label}
        </div>

        <span className="node-state">
          {status.toUpperCase()}
        </span>
      </div>

      <div className="node-metrics">
        <div>
          <span>CPU</span>
          <strong>{nodeData.cpu ?? 32}%</strong>
        </div>

        <div>
          <span>LAT</span>
          <strong>{nodeData.latency ?? 18}ms</strong>
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default NetworkNode;