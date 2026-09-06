"""REST routes — transport only (Vikash).

Source of truth: docs/BACKEND_SCHEMA.md §10, docs/APP_FLOW.md.

No domain logic. No API-side state. Each handler validates the request against
`models/`, delegates to the pipeline / state / a teammate port, and serialises
the result. Teammate ports that are unset raise `ModuleNotWired` -> 501.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.models.errors import ModuleNotWired, NotFound, PipelineError
from backend.models.faults import FaultRequest
from backend.models.run import RunRequest
from backend.models.state import NetworkState
from backend.state.mutations import set_active_faults
from backend.state.preview import preview

router = APIRouter()


def _ctx(request: Request):
    return request.app.state.ctx


def _require(port, who: str):
    if port is None:
        raise ModuleNotWired(f"{who} is not wired yet")
    return port


# --- network state --------------------------------------------------

@router.get("/network/state", response_model=NetworkState)
def get_network_state(request: Request) -> NetworkState:
    return _ctx(request).state.get_state()


@router.post("/network/reset", response_model=NetworkState)
def reset_network(request: Request) -> NetworkState:
    return _ctx(request).reset_state()


# --- telemetry -----------------------------------------------------

@router.get("/telemetry")
def get_telemetry(request: Request):
    ctx = _ctx(request)
    return _require(ctx.ports.telemetry, "telemetry/ (Sahil)").derive(ctx.state.get_state())


# --- faults ------------------------------------------------------

@router.get("/faults")
def list_faults(request: Request):
    ctx = _ctx(request)
    injector = _require(ctx.ports.faults, "faults/ (Sahil)")
    return {"faults": injector.active()}


def _commit_with_status(ctx, structural, reason: str):
    """Fold the NetworkModel's status recompute into ONE atomic batch."""
    snapshot = ctx.state.get_state()
    batch = list(structural)
    if ctx.ports.network_model is not None:
        batch += ctx.ports.network_model.recompute_status(preview(snapshot, batch))
    return ctx.state.apply_actions(batch, reason=reason)


@router.post("/faults", status_code=201)
def inject_fault(request: Request, body: FaultRequest):
    ctx = _ctx(request)
    injector = _require(ctx.ports.faults, "faults/ (Sahil)")
    fault, structural = injector.inject(body, ctx.state.get_state())
    structural = [*structural, set_active_faults([f.id for f in injector.active()])]
    state = _commit_with_status(ctx, structural, reason=f"fault {fault.id}")
    ctx.broadcaster.publish("fault", {"action": "injected", "fault": fault.model_dump(mode="json")}, state.version)
    return {"fault": fault, "state": state}


@router.delete("/faults/{fault_id}")
def clear_fault(request: Request, fault_id: str):
    ctx = _ctx(request)
    injector = _require(ctx.ports.faults, "faults/ (Sahil)")
    if fault_id not in {f.id for f in injector.active()}:
        raise NotFound(f"no active fault {fault_id!r}")
    structural = injector.clear(fault_id, ctx.state.get_state())
    structural = [*structural, set_active_faults([f.id for f in injector.active()])]
    state = _commit_with_status(ctx, structural, reason=f"clear fault {fault_id}")
    ctx.broadcaster.publish("fault", {"action": "cleared", "fault_id": fault_id}, state.version)
    return {"state": state}


# --- recovery -----------------------------------------------------

@router.post("/recovery/diagnose")
def recovery_diagnose(request: Request):
    try:
        return _ctx(request).pipeline.diagnose()
    except ModuleNotWired:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"diagnosis failed: {exc}") from exc


@router.post("/recovery/plan")
def recovery_plan(request: Request):
    try:
        diagnosis, candidates = _ctx(request).pipeline.plan()
    except ModuleNotWired:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"planning failed: {exc}") from exc
    return {"diagnosis": diagnosis, "candidates": candidates}


@router.post("/recovery/run")
def recovery_run(request: Request, body: RunRequest | None = None):
    auto_apply = True if body is None else body.auto_apply
    return _ctx(request).pipeline.run(auto_apply=auto_apply)
