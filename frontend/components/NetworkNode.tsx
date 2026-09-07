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
          <strong>{Math.round(nodeData.cpu ?? 32)}%</strong>
        </div>

        <div>
          <span>LAT</span>
          <strong>{Math.round(nodeData.latency ?? 18)}ms</strong>
        </div>

        <div>
          <span>LOAD</span>
          <strong>
            {nodeData.load !== undefined && nodeData.capacity
              ? `${Math.round((nodeData.load / nodeData.capacity) * 100)}%`
              : "--"}
          </strong>
        </div>
      </div>

      {nodeData.load !== undefined && nodeData.capacity !== undefined && (
        <div className="node-resource-bar" title={`Load: ${Math.round(nodeData.load)} / ${Math.round(nodeData.capacity)} units`}>
          <div
            className={`node-resource-fill ${
              nodeData.load / nodeData.capacity > 0.85
                ? "fill-high"
                : nodeData.load / nodeData.capacity > 0.65
                ? "fill-mid"
                : "fill-low"
            }`}
            style={{
              width: `${Math.min(100, Math.round((nodeData.load / nodeData.capacity) * 100))}%`,
            }}
          />
        </div>
      )}

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default NetworkNode;