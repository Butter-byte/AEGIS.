import NetworkNode from "./NetworkNode";
import NodeInspector from "./NodeInspector";

import { useCallback, useState } from "react";
import type { MouseEvent } from "react";
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

const nodeTypes = {
  network: NetworkNode,
};
const initialNodes: Node[] = [
  {
    id: "N1",
    position: { x: 100, y: 80 },
    type: "network",
    data: {
        label: "N1",
        status: "healthy",
        cpu: 42,
        latency: 18,
    },
  },
  {
    id: "N2",
    position: { x: 350, y: 80 },
    type: "network",
    data: {
        label: "N2",
        status: "healthy",
        cpu: 48,
        latency: 21,
    },
  },
  {
    id: "N3",
    position: { x: 100, y: 250 },
    type: "network",
    data: {
        label: "N3",
        status: "healthy",
        cpu: 27,
        latency: 14,
    },
  },
  {
    id: "N4",
    position: { x: 350, y: 250 },
    type: "network",
    data: {
        label: "N4",
        status: "degraded",
        cpu: 91,
        latency: 184,
    },
  },
  {
    id: "N5",
    position: { x: 600, y: 165 },
    type: "network",
    data: {
        label: "N5",
        status: "healthy",
        cpu: 41,
        latency: 24,
    },
  },
];

const initialEdges: Edge[] = [
  { id: "N1-N2", source: "N1", target: "N2" },
  { id: "N1-N3", source: "N1", target: "N3" },
  { id: "N2-N4", source: "N2", target: "N4" },
  { id: "N3-N4", source: "N3", target: "N4" },
  { id: "N2-N5", source: "N2", target: "N5" },
  { id: "N4-N5", source: "N4", target: "N5" },
];

type NetworkGraphProps = {
  onEvent: (event: string) => void;
};

function NetworkGraph({ onEvent }: NetworkGraphProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;

  const onNodeClick = useCallback(
    (_event: MouseEvent, node: Node) => {
        setSelectedNodeId(node.id);
    },
    [],
);

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((currentEdges) => addEdge(connection, currentEdges));
    },
    [setEdges],
  );

  const isolateNode = useCallback(() => {
    if (!selectedNode) return;

    const nodeId = selectedNode.id;

    // Mark the node as failed
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

  // Remove all connections to/from the failed node
  setEdges((currentEdges) =>
    currentEdges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    ),
  );

  // Record the event
    onEvent(`Node ${nodeId} isolated.`);
}, [selectedNode, setNodes, setEdges, onEvent]);

  return (
    <div className="network-container">
        <div className="network-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            proOptions={{ hideAttribution: true }}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
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