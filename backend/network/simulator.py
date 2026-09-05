import networkx as nx
from backend.models.state import NetworkState, NodeState, EdgeState

class NetworkSimulator:
    def __init__(self):
        self.graph = nx.Graph()
        self._build_initial_topology()

    def _build_initial_topology(self):
        """Builds a small seed topology (5–10 nodes for v0.1, expanding to 15–30 tomorrow)."""
        # Define basic nodes
        for i in range(1, 8):
            node_id = f"N{i}"
            self.graph.add_node(
                node_id,
                cpu=25.0,
                latency=10.0,
                packet_loss=0.01,
                status="healthy"
            )

        # Define initial edges/mesh links
        edges = [
            ("N1", "N2"), ("N1", "N3"),
            ("N2", "N4"), ("N3", "N4"),
            ("N4", "N5"), ("N4", "N6"),
            ("N5", "N7"), ("N6", "N7")
        ]
        for u, v in edges:
            self.graph.add_edge(u, v, bandwidth=1000.0, latency=5.0, packet_loss=0.0, status="active")

    def get_state(self) -> NetworkState:
        """Returns the single source of truth state for API and frontend."""
        nodes = {
            node_id: NodeState(id=node_id, **data)
            for node_id, data in self.graph.nodes(data=True)
        }
        edges = [
            EdgeState(source=u, target=v, **data)
            for u, v, data in self.graph.edges(data=True)
        ]
        return NetworkState(nodes=nodes, edges=edges)

    def kill_node(self, node_id: str) -> NetworkState:
        """Injects a node failure and updates the state."""
        if node_id in self.graph.nodes:
            self.graph.nodes[node_id]["status"] = "failed"
            self.graph.nodes[node_id]["cpu"] = 0.0
            self.graph.nodes[node_id]["packet_loss"] = 1.0
            
            # Mark adjacent links as inactive
            for neighbor in self.graph.neighbors(node_id):
                self.graph.edges[node_id, neighbor]["status"] = "failed"
                
        return self.get_state()

    def restart_node(self, node_id: str) -> NetworkState:
    # """Restores a failed node back to healthy state."""
        if node_id in self.graph.nodes:
            self.graph.nodes[node_id]["status"] = "healthy"
            self.graph.nodes[node_id]["cpu"] = 25.0
            self.graph.nodes[node_id]["packet_loss"] = 0.01
            
            # Restore adjacent links to active
            for neighbor in self.graph.neighbors(node_id):
                self.graph.edges[node_id, neighbor]["status"] = "active"
                
        return self.get_state()