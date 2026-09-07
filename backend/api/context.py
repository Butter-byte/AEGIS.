"""AppContext — the composed object graph, built once at startup.

Simple constructor injection. No DI framework, no service container (ponytail).
`main.py` builds one and stashes it on `app.state.ctx`; routes read it from there.

`api/` imports only `models`, `state`, `pipeline`, `config` (ARCHITECTURE §8).
The Executor is owned by the Pipeline (invariant 10), so it is not referenced
here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.api.ws import Broadcaster
from backend.config import DEFAULT_POLICY
from backend.models.state import NetworkState
from backend.pipeline import Pipeline
from backend.state.manager import StateManager
from backend.network.simulator import build_seed
from backend.telemetry import TelemetryEngine
from backend.faults import FaultInjector
from backend.diagnosis import HeuristicDiagnoser
from backend.recovery import RecoveryPlanner
from backend.simulation.twin import DigitalTwin
from backend.safety import SafetyEngine

# Single seed source for the running simulator. Nothing else constructs the
# canonical live NetworkState.
SeedFactory = Callable[[], NetworkState]
_seed_factory: SeedFactory = build_seed


@dataclass
class AppContext:
    state: StateManager
    pipeline: Pipeline
    broadcaster: Broadcaster
    seed_factory: SeedFactory
    faults: FaultInjector
    telemetry: TelemetryEngine

    @classmethod
    def build(cls, seed_factory: SeedFactory = _seed_factory) -> "AppContext":
        state = StateManager(seed_factory())
        broadcaster = Broadcaster()

        # StateManager notifies the broadcaster on every committed mutation.
        state.subscribe(lambda snapshot: broadcaster.publish(
            "state",
            {"state": snapshot.model_dump(mode="json")},
            snapshot.version,
        ))

        faults = FaultInjector(state)
        telemetry = TelemetryEngine()

        pipeline = Pipeline(
            state=state,
            policy=DEFAULT_POLICY,
            publisher=broadcaster.publish,
            telemetry=telemetry,
            faults=faults,
            diagnoser=HeuristicDiagnoser(),
            planner=RecoveryPlanner(),
            twin=DigitalTwin(),
            safety=SafetyEngine(),
        )
        return cls(state=state, pipeline=pipeline, broadcaster=broadcaster, seed_factory=seed_factory, faults=faults, telemetry=telemetry)

    def reset_state(self) -> NetworkState:
        """Rebuild the network from the seed (a normal versioned mutation)."""
        self.faults.reset()
        return self.state.reset(self.seed_factory())
