"""Ports — the interfaces teammate modules must satisfy (Vikash).

Source of truth: docs/TRD.md §"Module ports".

The pipeline depends on these Protocols, never on concrete teammate packages.
Each port is filled by:
  * the real teammate module once it lands, or
  * a deterministic fake (`tests/fakes.py`) for integration tests, or
  * nothing — in which case the composition root leaves it unset and the
    matching endpoint returns `module_not_wired` (501).

Ownership per port is in the docstring. NOTHING here imports a teammate package.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.models.diagnosis import Diagnosis
from backend.models.faults import Fault, FaultRequest
from backend.models.recovery import RecoveryPlan
from backend.models.safety import PolicyConfig, SafetyDecision
from backend.models.state import NetworkState
from backend.models.telemetry import Telemetry
from backend.models.twin import SimulationResult
from backend.state.mutations import Mutation


@runtime_checkable
class SeedSource(Protocol):
    """Owner: Sahil (`backend/network/`). Produces the initial NetworkState."""

    def build_seed(self) -> NetworkState: ...


@runtime_checkable
class TelemetrySource(Protocol):
    """Owner: Sahil (`backend/telemetry/`). Pure projection of state."""

    def derive(self, state: NetworkState) -> Telemetry: ...


@runtime_checkable
class NetworkModel(Protocol):
    """Owner: Sahil (`backend/network/`).

    Two jobs the integration layer delegates:

      * `recompute_status(state)` — given a state whose STRUCTURAL fields were just
        changed (a fault applied, a recovery plan's actions applied), return the
        status-only mutations that make node / edge / service `status` consistent
        with the topology + metrics. Pure, deterministic. Vikash's fault route and
        Executor call this and fold the result into the SAME atomic batch, so one
        operation is still one version bump.
      * `resolve_path(...)` — a viable ordered node path for a service (see
        `backend.execution.translate.PathResolver`). Used when a plan reroutes or
        migrates a service.
    """

    def recompute_status(self, state: NetworkState) -> list[Mutation]: ...

    def resolve_path(
        self,
        service_id: str,
        state: NetworkState,
        *,
        avoid_nodes: list[str] | None = None,
        avoid_edges: list[str] | None = None,
        new_host: str | None = None,
    ) -> list[str] | None: ...


@runtime_checkable
class FaultInjector(Protocol):
    """Owner: Sahil (`backend/faults/`).

    `inject` / `clear` return the mechanical mutations for StateManager to apply
    — they do NOT mutate state themselves. `active` lists tracked faults.
    """

    def inject(self, request: FaultRequest, state: NetworkState) -> tuple[Fault, list[Mutation]]: ...

    def clear(self, fault_id: str, state: NetworkState) -> list[Mutation]: ...

    def active(self) -> list[Fault]: ...


@runtime_checkable
class Diagnoser(Protocol):
    """Owner: Yyash (`backend/diagnosis/`). Advisory. Returns data only."""

    def diagnose(self, state: NetworkState, telemetry: Telemetry, active_faults: list[Fault]) -> Diagnosis: ...


@runtime_checkable
class RecoveryPlanner(Protocol):
    """Owner: Yyash (`backend/recovery/`).

    Returns candidate plans using the CLOSED action vocabulary, each with
    `based_on_version` set to the input state's version. Returns data only.
    """

    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]: ...


@runtime_checkable
class DigitalTwin(Protocol):
    """Owner: Sahil (`backend/twin/`).

    Receives a NetworkState VALUE (deep copy) + one plan. Must not touch live
    state. Deterministic: same inputs -> same SimulationResult.
    """

    def validate(self, state_copy: NetworkState, plan: RecoveryPlan) -> SimulationResult: ...


@runtime_checkable
class SafetyGate(Protocol):
    """Owner: Hrishi (`backend/safety/`).

    Deterministic. Consumes only structured data — never AI text. `approved` iff
    no critical violation.
    """

    def evaluate(
        self,
        before: NetworkState,
        simulation: SimulationResult,
        plan: RecoveryPlan,
        policy: PolicyConfig,
    ) -> SafetyDecision: ...
