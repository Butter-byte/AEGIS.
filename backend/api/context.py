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
from backend.state.seed import build_seed

# TEMPORARY seed source. Single swap point: when `backend.network.build_seed`
# exists (Sahil), change this one alias. Nothing else references the seed.
SeedFactory = Callable[[], NetworkState]
_seed_factory: SeedFactory = build_seed


@dataclass
class AppContext:
    state: StateManager
    pipeline: Pipeline
    broadcaster: Broadcaster
    seed_factory: SeedFactory

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

        pipeline = Pipeline(
            state=state,
            policy=DEFAULT_POLICY,
            publisher=broadcaster.publish,
            # telemetry / faults / diagnoser / planner / twin / safety:
            # left as NotImplemented* stubs until teammate modules land.
        )
        return cls(state=state, pipeline=pipeline, broadcaster=broadcaster, seed_factory=seed_factory)

    def reset_state(self) -> NetworkState:
        """Rebuild the network from the seed (a normal versioned mutation)."""
        return self.state.reset(self.seed_factory())
