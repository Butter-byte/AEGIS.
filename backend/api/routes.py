"""REST routes — transport only.

Source of truth: docs/TRD.md §5, docs/BACKEND_SCHEMA.md §8.

The state, telemetry, fault, diagnosis, planning, and recovery routes all use
the services composed by AppContext. POST /recovery/run executes the complete
deterministic MVP pipeline.

No domain logic here. No API-side state — GET /network/state returns the
canonical StateManager state.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.models.errors import NotImplementedYet, PipelineError
from backend.models.faults import FaultRequest
from backend.models.run import PlanRequest, RunRequest
from backend.models.state import NetworkState

router = APIRouter()

def _ctx(request: Request):
    return request.app.state.ctx


# --- liveness ----------------------------------------------------------------

@router.get("/health")
def health() -> dict[str, str]:
    """Cheap liveness probe — no AppContext access, used by the Docker healthcheck."""
    return {"status": "ok"}


# --- network state (foundation, fully implemented) -----------------------

@router.get("/network/state", response_model=NetworkState)
def get_network_state(request: Request) -> NetworkState:
    return _ctx(request).state.get_state()


@router.post("/network/reset", response_model=NetworkState)
async def reset_network(request: Request) -> NetworkState:
    return _ctx(request).reset_state()


# --- telemetry / faults -------------------------------------------------

@router.get("/telemetry")
def get_telemetry(request: Request):
    return _ctx(request).telemetry.derive(_ctx(request).state.get_state())


@router.get("/faults")
def list_faults(request: Request):
    return _ctx(request).faults.active()


@router.post("/faults", status_code=201)
async def inject_fault(request: Request, body: FaultRequest):
    return _ctx(request).faults.inject(body)


@router.delete("/faults/{fault_id}")
async def clear_fault(request: Request, fault_id: str):
    _ctx(request).faults.clear(fault_id)
    return {"cleared": fault_id}


# --- recovery -------------------------------------------------------

@router.post("/recovery/diagnose")
def recovery_diagnose(request: Request):
    try:
        return _ctx(request).pipeline.diagnose()
    except (NotImplementedError, PipelineError) as exc:
        raise NotImplementedYet(f"diagnosis unavailable: {exc}") from exc


@router.post("/recovery/plan")
def recovery_plan(request: Request, body: PlanRequest | None = None):
    try:
        diagnosis, candidates = _ctx(request).pipeline.plan(
            diagnosis_id=body.diagnosis_id if body else None
        )
        return {"diagnosis": diagnosis, "candidates": candidates}
    except (NotImplementedError, PipelineError) as exc:
        raise NotImplementedYet(f"planning unavailable: {exc}") from exc


@router.post("/recovery/run")
async def recovery_run(request: Request, body: RunRequest | None = None):
    auto_apply = True if body is None else body.auto_apply
    return _ctx(request).pipeline.run(auto_apply=auto_apply)
