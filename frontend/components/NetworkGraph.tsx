import NetworkNode from "./NetworkNode";
import NodeInspector from "./NodeInspector";
import type { NetworkState } from "../types/network";
import { useCallback, useEffect, useMemo, useState } from "react";
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

type NetworkGraphProps = {
  networkState: NetworkState | null;
  onEvent: (event: string) => void;
};

function NetworkGraph({ networkState, onEvent }: NetworkGraphProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const networkNodes = useMemo<Node[]>(() => {
    if (!networkState) return [];

    return Object.values(networkState.nodes).map((node, index) => ({
      id: node.id,
      position: {
        x: 100 + (index % 3) * 250,
        y: 80 + Math.floor(index / 3) * 170,
      },
      type: "network",
      data: {
        label: node.id,
        status: node.status,
        cpu: node.cpu_percent,
        latency: node.latency_ms,
      },
    }));
  }, [networkState]);

  const networkEdges = useMemo<Edge[]>(() => {
    if (!networkState) return [];

    return networkState.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    }));
  }, [networkState]);

  const [nodes, setNodes, onNodesChange] = useNodesState(networkNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(networkEdges);
  useEffect(() => {
  setNodes(networkNodes);
  setEdges(networkEdges);
  }, [networkNodes, networkEdges, setNodes, setEdges]);

  const selectedNode =
    nodes.find((node) => node.id === selectedNodeId) ?? null;

  const onNodeClick = useCallback(
    (_event: MouseEvent, node: Node) => {
      setSelectedNodeId(node.id);
    },
    [],
  );

  const isolateNode = useCallback(() => {
  if (!selectedNode) return;

  const nodeId = selectedNode.id;

  setNodes((currentNodes) =>
    currentNodes.map((node) => {
      if (node.id !== nodeId) return node;

      return {
        ...node,
        data: {
          ...node.data,
          status: "failed",
        },
      };
    }),
  );

  setEdges((currentEdges) =>
    currentEdges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    ),
  );

  onEvent(`Node ${nodeId} isolated.`);
}, [selectedNode, setNodes, setEdges, onEvent]);

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
          fitView
        >
          <Background />
        </ReactFlow>
      </div>

      <NodeInspector
        node={selectedNode}
        onIsolate={isolateNode}
      />
    </div>
  );
}

export default NetworkGraph;