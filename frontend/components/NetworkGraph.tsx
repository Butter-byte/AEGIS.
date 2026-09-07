import NetworkNode from "./NetworkNode";
import NodeInspector from "./NodeInspector";
import type { EdgeStatus, NetworkNodeData, NetworkState } from "../types/network";
import { useCallback, useEffect, useMemo } from "react";
import type { MouseEvent } from "react";
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const nodeTypes = {
  network: NetworkNode,
};

// Edge appearance derived purely from the backend EdgeStatus. A selected edge is
// overpainted with a bright stroke so selection stays visible regardless of status.
const EDGE_VISUALS: Record<EdgeStatus, { stroke: string; width: number; dash?: string; animated?: boolean }> = {
  active: { stroke: "#3a4553", width: 1 },
  congested: { stroke: "#d29922", width: 2, animated: true },
  failed: { stroke: "#f85149", width: 2, dash: "6 4" },
};

type NetworkGraphProps = {
  networkState: NetworkState | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
  onIsolateSelected: () => void;
  actionPending: boolean;
};

function NetworkGraph({
  networkState,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
  onIsolateSelected,
  actionPending,
}: NetworkGraphProps) {
  const networkNodes = useMemo<Node<NetworkNodeData>[]>(() => {
    if (!networkState) return [];

    return Object.values(networkState.nodes).map((node, index) => ({
      id: node.id,
      position: {
        x: 100 + (index % 3) * 250,
        y: 80 + Math.floor(index / 3) * 170,
      },
      type: "network",
      selected: node.id === selectedNodeId,
      data: {
        label: node.id,
        status: node.status,
        cpu: node.cpu_percent,
        latency: node.latency_ms,
      },
    }));
  }, [networkState, selectedNodeId]);

  const networkEdges = useMemo<Edge[]>(() => {
    if (!networkState) return [];

    return networkState.edges.map((edge) => {
      const isSelected = edge.id === selectedEdgeId;
      const visual = EDGE_VISUALS[edge.status] ?? EDGE_VISUALS.active;
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        selected: isSelected,
        animated: visual.animated ?? false,
        style: {
          stroke: isSelected ? "#e6edf3" : visual.stroke,
          strokeWidth: isSelected ? 3 : visual.width,
          strokeDasharray: visual.dash,
        },
      };
    });
  }, [networkState, selectedEdgeId]);

  const [nodes, setNodes, onNodesChange] =
    useNodesState<Node<NetworkNodeData>>(networkNodes);

  const [edges, setEdges, onEdgesChange] =
    useEdgesState(networkEdges);

  useEffect(() => {
    setNodes(networkNodes);
    setEdges(networkEdges);
  }, [networkNodes, networkEdges, setNodes, setEdges]);

  const selectedNode =
    nodes.find((node) => node.id === selectedNodeId) ?? null;

  const onNodeClick = useCallback(
    (_event: MouseEvent, node: Node<NetworkNodeData>) => {
      onSelectNode(node.id);
    },
    [onSelectNode],
  );

  const onEdgeClick = useCallback(
    (_event: MouseEvent, edge: Edge) => {
      onSelectEdge(edge.id);
    },
    [onSelectEdge],
  );

  return (
    <div className="network-container">
      <div className="network-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          fitView
        >
          <Background />
        </ReactFlow>
      </div>

      <NodeInspector
        node={selectedNode}
        onIsolate={onIsolateSelected}
        disabled={actionPending}
      />
    </div>
  );
}

export default NetworkGraph;
