"""REST routes — transport only.

Source of truth: docs/TRD.md §5, docs/BACKEND_SCHEMA.md §8.

Fully implemented (foundation): GET /network/state, POST /network/reset.
Stubbed (teammate modules not wired): telemetry, faults, diagnose, plan  -> 501.
POST /recovery/run executes the real pipeline and returns its honest outcome.

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


# --- network state (foundation, fully implemented) -----------------------

@router.get("/network/state", response_model=NetworkState)
def get_network_state(request: Request) -> NetworkState:
    return _ctx(request).state.get_state()


@router.post("/network/reset", response_model=NetworkState)
async def reset_network(request: Request) -> NetworkState:
    return _ctx(request).reset_state()


# --- telemetry / faults (Sahil — not wired) ---------------------------

@router.get("/telemetry")
def get_telemetry(request: Request):
    raise NotImplementedYet("telemetry is not wired yet — telemetry/ (Sahil)")


@router.get("/faults")
def list_faults(request: Request):
    raise NotImplementedYet("fault listing is not wired yet — faults/ (Sahil)")


@router.post("/faults", status_code=201)
async def inject_fault(request: Request, body: FaultRequest):
    raise NotImplementedYet("fault injection is not wired yet — faults/ (Sahil)")


@router.delete("/faults/{fault_id}")
async def clear_fault(request: Request, fault_id: str):
    raise NotImplementedYet("fault clearing is not wired yet — faults/ (Sahil)")


# --- recovery -------------------------------------------------------

@router.post("/recovery/diagnose")
def recovery_diagnose(request: Request):
    try:
        return _ctx(request).pipeline.diagnose()
    except (NotImplementedError, PipelineError) as exc:
        raise NotImplementedYet(f"diagnosis is not wired yet — ai/ (Yyash): {exc}") from exc


@router.post("/recovery/plan")
def recovery_plan(request: Request, body: PlanRequest | None = None):
    try:
        diagnosis, candidates = _ctx(request).pipeline.plan(
            diagnosis_id=body.diagnosis_id if body else None
        )
        return {"diagnosis": diagnosis, "candidates": candidates}
    except (NotImplementedError, PipelineError) as exc:
        raise NotImplementedYet(f"planning is not wired yet — ai/ (Yyash): {exc}") from exc


@router.post("/recovery/run")
async def recovery_run(request: Request, body: RunRequest | None = None):
    auto_apply = True if body is None else body.auto_apply
    return _ctx(request).pipeline.run(auto_apply=auto_apply)
