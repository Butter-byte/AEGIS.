from __future__ import annotations

from backend.models.common import edge_id_for, new_fault_id, utcnow
from backend.models.enums import EdgeStatus, FaultType, NodeStatus
from backend.models.faults import Fault, FaultRequest
from backend.state.manager import StateManager, StateInvariantError
from backend.state.mutations import set_active_faults, set_edge, set_node


class FaultInjector:
    def __init__(self, state: StateManager) -> None:
        self._state = state
        self._faults: dict[str, Fault] = {}

    def active(self) -> list[Fault]:
        return list(self._faults.values())

    def inject(self, request: FaultRequest) -> Fault:
        state = self._state.get_state()
        fault_id = new_fault_id()
        params = request.params or {}
        mutations = []
        if request.type in {FaultType.kill_node, FaultType.degrade_node, FaultType.overload_node, FaultType.traffic_spike}:
            if request.target not in state.nodes:
                raise StateInvariantError(f"unknown node {request.target!r}")
            if request.type == FaultType.kill_node:
                mutations.append(set_node(request.target, status=NodeStatus.failed.value, cpu_percent=0.0, packet_loss_percent=100.0))
            elif request.type == FaultType.degrade_node:
                mutations.append(set_node(request.target, status=NodeStatus.degraded.value, cpu_percent=85.0, latency_ms=80.0))
            else:
                mutations.append(set_node(request.target, status=NodeStatus.degraded.value, cpu_percent=95.0, load=950.0))
        else:
            edge_id = request.target if "-" in request.target else edge_id_for(*request.target.split(":"))
            edge = next((edge for edge in state.edges if edge.id == edge_id), None)
            if edge is None:
                raise StateInvariantError(f"unknown edge {request.target!r}")
            if request.type == FaultType.cut_edge:
                mutations.append(set_edge(edge_id, status=EdgeStatus.failed.value, packet_loss_percent=100.0))
            else:
                mutations.append(set_edge(edge_id, status=EdgeStatus.congested.value, utilization_percent=95.0, latency_ms=100.0))
        fault = Fault(id=fault_id, type=request.type, target=request.target, params=params, created_at=utcnow())
        mutations.append(set_active_faults([*state.active_fault_ids, fault_id]))
        self._state.apply_actions(mutations, reason=f"inject {fault_id}")
        self._faults[fault_id] = fault
        return fault

    def clear(self, fault_id: str) -> None:
        fault = self._faults.pop(fault_id, None)
        if fault is None:
            raise StateInvariantError(f"unknown fault {fault_id!r}")
        state = self._state.get_state()
        mutations = [set_active_faults([fid for fid in state.active_fault_ids if fid != fault_id])]
        if fault.target in state.nodes:
            mutations.append(set_node(fault.target, status=NodeStatus.healthy.value, cpu_percent=35.0, latency_ms=12.0, packet_loss_percent=0.0, load=450.0))
        else:
            mutations.append(set_edge(fault.target, status=EdgeStatus.active.value, packet_loss_percent=0.0, utilization_percent=45.0, latency_ms=5.0))
        self._state.apply_actions(mutations, reason=f"clear {fault_id}")