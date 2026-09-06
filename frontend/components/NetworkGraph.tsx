import NetworkNode from "./NetworkNode";
import NodeInspector from "./NodeInspector";
import type { NetworkNodeData, NetworkState } from "../types/network";
import { injectFault } from "../services/api";
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

  const networkNodes = useMemo<Node<NetworkNodeData>[]>(() => {
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
      setSelectedNodeId(node.id);
    },
    [],
  );

  const isolateNode = useCallback(async () => {
    if (!selectedNode) return;

    const nodeId = selectedNode.id;

    try {
      await injectFault("kill_node", nodeId);
      onEvent(`Isolation requested for node ${nodeId}.`);
    } catch (error) {
      console.error("Failed to isolate node:", error);
      onEvent(`Failed to isolate node ${nodeId}.`);
    }
  }, [selectedNode, onEvent]);

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