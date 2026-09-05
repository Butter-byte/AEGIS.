from fastapi import APIRouter, HTTPException
from backend.network.simulator import NetworkSimulator

router = APIRouter()
sim = NetworkSimulator()

@router.get("/network/state")
def get_current_state():
    return sim.get_state()

@router.post("/network/fault/kill-node/{node_id}")
def inject_kill_node(node_id: str):
    if node_id not in sim.graph.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    updated_state = sim.kill_node(node_id)
    return {"message": f"Node {node_id} set to failed", "state": updated_state}

@router.post("/network/fault/restart-node/{node_id}")
def inject_restart_node(node_id: str):
    if node_id not in sim.graph.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    updated_state = sim.restart_node(node_id)
    return {"message": f"Node {node_id} restarted and healthy", "state": updated_state}