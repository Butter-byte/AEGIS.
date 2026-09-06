"""AppContext — the composed object graph, built once at startup (Vikash).

Constructor injection, no DI framework. `backend/main.py` builds one and stashes
it on `app.state.ctx`; routes read it from there.

`api/` imports only `models`, `state`, `pipeline`, `events`, `config`. It does
NOT import `execution/` — the Executor is owned by the Pipeline (the only caller
of execution).

Teammate ports default to unset: the pipeline reports `module_not_wired` for the
matching endpoints until `main.py` (or a test) injects a real module or a fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.events.broadcaster import Broadcaster
from backend.models.safety import PolicyConfig
from backend.models.state import NetworkState
from backend.pipeline.orchestrator import Pipeline
from backend.pipeline.ports import (
    Diagnoser,
    DigitalTwin,
    FaultInjector,
    NetworkModel,
    RecoveryPlanner,
    SafetyGate,
    SeedSource,
    TelemetrySource,
)
from backend.state.manager import StateManager
from backend.state.seed import ScaffoldSeedSource


@dataclass
class Ports:
    """Every teammate-owned dependency. Any left None => that endpoint 501s."""

    seed_source: SeedSource = field(default_factory=ScaffoldSeedSource)
    network_model: NetworkModel | None = None
    telemetry: TelemetrySource | None = None
    faults: FaultInjector | None = None
    diagnoser: Diagnoser | None = None
    planner: RecoveryPlanner | None = None
    twin: DigitalTwin | None = None
    safety: SafetyGate | None = None


@dataclass
class AppContext:
    state: StateManager
    pipeline: Pipeline
    broadcaster: Broadcaster
    ports: Ports

    @classmethod
    def build(cls, ports: Ports | None = None, policy: PolicyConfig | None = None) -> "AppContext":
        ports = ports or Ports()
        state = StateManager(ports.seed_source.build_seed())
        broadcaster = Broadcaster()

        # StateManager notifies the broadcaster on every committed mutation.
        state.subscribe(
            lambda snap: broadcaster.publish("state", {"state": snap.model_dump(mode="json")}, snap.version)
        )

        pipeline = Pipeline(
            state=state,
            network_model=ports.network_model,
            telemetry=ports.telemetry,
            faults=ports.faults,
            diagnoser=ports.diagnoser,
            planner=ports.planner,
            twin=ports.twin,
            safety=ports.safety,
            policy=policy or PolicyConfig(),
            publisher=broadcaster.publish,
        )
        return cls(state=state, pipeline=pipeline, broadcaster=broadcaster, ports=ports)

    def reset_state(self) -> NetworkState:
        """Rebuild the network from the seed (a normal versioned mutation)."""
        return self.state.reset(self.ports.seed_source.build_seed())
