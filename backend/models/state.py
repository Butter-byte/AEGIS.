from typing import Dict, Literal
from pydantic import BaseModel, Field

class NodeState(BaseModel):
    id: str
    cpu: float = Field(default=20.0, description="CPU utilization percentage")
    latency: float = Field(default=15.0, description="Latency in ms")
    packet_loss: float = Field(default=0.0, description="Packet loss ratio 0.0-1.0")
    status: Literal["healthy", "degraded", "failed", "quarantined"] = "healthy"

class EdgeState(BaseModel):
    source: str
    target: str
    bandwidth: float = 1000.0  # Mbps
    latency: float = 5.0       # ms
    packet_loss: float = 0.0
    status: Literal["active", "congested", "failed"] = "active"

class NetworkState(BaseModel):
    nodes: Dict[str, NodeState]
    edges: list[EdgeState]