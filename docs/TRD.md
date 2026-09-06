# AEGIS — Technical Requirements & Architecture (TRD)

**Owner:** Vikash (System Architecture + Integration Lead)
**Companions:** `BACKEND_SCHEMA.md` (field-level contracts — source of truth),
`APP_FLOW.md` (flows), `UI_UX_BRIEF.md` (frontend), `IMPLEMENTATION_PLAN.md` (phases).

This document is the authoritative **architecture**. Where it and
`BACKEND_SCHEMA.md` overlap, this file defines *boundaries and rules*;
`BACKEND_SCHEMA.md` defines *shapes*. There is no separate `ARCHITECTURE.md`.

---

## 1. Goals & constraints

| # | Requirement |
|---|---|
| T1 | One FastAPI process, one worker (`uvicorn --workers 1`), in-memory state |
| T2 | Python 3.11–3.13, Pydantic v2, FastAPI, `networkx`. Frontend: Vite + React + `@xyflow/react` |
| T3 | No database, message queue, cache server, or container runtime for dev |
| T4 | State not persisted — process restart = fresh seed |
| T5 | Everything crossing a module boundary conforms to `BACKEND_SCHEMA.md` |
| T6 | The invariants in §3 hold at all times |
| T7 | A full recovery run completes in < 5 s with the deterministic modules |
| T8 | Demoable end-to-end with no live LLM call |

---

## 2. Ownership map (who implements what)

**This is a four-person project. A Claude session working on AEGIS implements ONE
owner's scope at a time.** The current backbone was built for **Vikash**.

| Package / area | Owner | Vikash may… |
|---|---|---|
| `backend/models/` | **Vikash** | own it — the shared contract |
| `backend/state/` (StateManager, mutations, preview) | **Vikash** | own it |
| `backend/pipeline/` (orchestrator, ports) | **Vikash** | own it |
| `backend/execution/` (executor, translate) | **Vikash** | own it |
| `backend/events/` (broadcaster) | **Vikash** | own it |
| `backend/api/` (routes, ws, errors, context) | **Vikash** | own it |
| `backend/main.py` | **Vikash** | own it |
| `tests/` (models, contracts, state, api, ws, pipeline, safety-boundary, E2E), `tests/fakes.py` | **Vikash** | own it |
| `docs/` | **Vikash** | own it |
| `backend/network/` (topology, graph, pathfinding, `recompute_status`) | **Sahil** | define the port + a fake; **not** implement |
| `backend/telemetry/` (derive) | **Sahil** | define the port + a fake; **not** implement |
| `backend/faults/` (FaultInjector) | **Sahil** | define the port + a fake; **not** implement |
| `backend/twin/` (Digital Twin) | **Sahil** | define the port + a fake; **not** implement |
| `backend/diagnosis/` (Diagnoser) | **Yyash** | define the port + a fake; **not** implement |
| `backend/recovery/` (RecoveryPlanner) | **Yyash** | define the port + a fake; **not** implement |
| `backend/safety/` (SafetyGate) | **Hrishi** | define the port + a fake; **not** implement |
| `backend/scenarios/` | **Sahil + all** | leave as placeholder |
| `frontend/` | **Hrishi** | define REST/WS contracts only; **not** implement any UI |

Teammate packages currently contain only `__init__.py` + a `README.md` naming the
owner. `tests/test_architecture_boundaries.py` fails if Vikash code appears there.

---

## 3. Architectural invariants (non-negotiable)

Frozen. Changing one requires all four owners.

1. **`NetworkState` is the single source of truth.**
2. **`StateManager` is the only component that mutates live `NetworkState`.**
   Mutations enter through `apply_actions()` only, as mechanical primitives.
3. **No AI output touches the network directly.** The Diagnoser and
   RecoveryPlanner return *data*. Downstream deterministic components decide what,
   if anything, is acted on.
4. **AI output conforms to a closed `RecoveryAction` schema** — no free-form
   strings, shell commands, configs, code, or SQL.
5. **The AI cannot invoke execution.** `backend/diagnosis/` and
   `backend/recovery/` may import `backend/models/` only.
6. **The Digital Twin operates on an isolated deep copy** and cannot mutate live
   state. `backend/twin/` may not import `backend/state/` or `backend/execution/`.
7. **The Safety Gate is deterministic** — same inputs ⇒ same `SafetyDecision` —
   and **independent of AI reasoning**. `backend/safety/` may import
   `backend/models/` only; no I/O, no randomness, no wall-clock branching.
8. **Execution applies only safety-approved plans** for the *current* version.
9. **No second authoritative state store** may emerge — the frontend renders
   server state; it is not a parallel model.
10. **WebSocket is observation-only.** Inbound frames are ignored. It is never a
    mutation path.
11. **Service health is judged against the assigned path** (`ServiceState.path`),
    reassigned only by an executed `reroute`/`migrate_service` —
    `BACKEND_SCHEMA.md` §2.3.
12. **Hackathon-appropriate:** one process, one worker, in-memory, one seed, no
    databases/queues/orchestrators.

### 3.1 The core invariant, made concrete

```
Diagnoser ─► RecoveryPlanner ─► [schema gate] ─► Digital Twin ─► Safety Gate ─► Executor ─► StateManager
  data          data              reject if         copy in,        approve/          only if        the only
  only          only              malformed         result out      reject            approved       writer
```

Two enforcement points, both Vikash-owned and both tested:

- **Schema gate** (`backend/models/validation.parse_plan`): a plan that is not
  well-formed over known ids never advances. Test: `tests/test_schema_validation.py`.
- **Executor** (`backend/execution/executor.py`): refuses any plan lacking an
  `approved` `SafetyDecision` whose `plan_id` matches and whose `based_on_version`
  equals the current version. Test: `tests/test_safety_boundary.py`.

---

## 4. Authoritative state — StateManager (`backend/state/`)

```
class StateManager:
    current_version() -> int
    get_state() -> NetworkState          # deep copy; alias: snapshot()
    apply_actions(mutations, reason) -> NetworkState
    reset(seed) -> NetworkState
    subscribe(callback)                  # the WS layer registers here
```

Rules:

- `get_state()` returns `live.model_copy(deep=True)` — no caller holds the live object.
- `apply_actions()` is the **only** mutation path. It: builds a draft from the
  current state + mechanical primitives → sets `version += 1`, `updated_at` →
  **fully re-validates** the draft against the `NetworkState` model → swaps
  atomically → notifies subscribers. On validation failure it raises
  `StateInvariantError` and the live state is untouched.
- Callers of `apply_actions()`: **`backend/faults/` (via the API route) and
  `backend/execution/` only.**
- `version` is never reset — `reset()` is a normal forward mutation. This keeps
  the frontend's stale-frame rule (drop `version <= current`) always correct.
- A subscriber that raises is isolated: the mutation still commits.
- No locking — single worker, event loop.

### 4.1 Mutation primitives (`backend/state/mutations.py`)

`apply_actions()` does not take `RecoveryAction`s or `Fault`s. It takes
`SetNodeFields` / `SetEdgeFields` / `SetServiceFields` / `SetActiveFaults` —
mechanical "merge these fields" ops with no domain semantics. Translating a domain
operation into primitives is the caller's job (`BACKEND_SCHEMA.md` §13):

- `backend/faults/` (Sahil) — a `Fault` + params → primitives.
- `backend/execution/` (Vikash) — an approved `RecoveryPlan` → primitives.

### 4.2 Status recompute (`NetworkModel` port)

Structural mutations (a fault applied, a plan's actions applied) leave `status`
fields stale. Deriving `NodeStatus`/`EdgeStatus`/`ServiceStatus` from the topology
is **Sahil's** (`backend/network/`), exposed as
`NetworkModel.recompute_status(state) -> list[Mutation]`. The fault route and the
Executor call it against a **preview** of their structural batch
(`backend/state/preview.py`) and fold the result into the **same** atomic
`apply_actions` call — one operation, one version bump.

---

## 5. Module ports (`backend/pipeline/ports.py`)

The pipeline depends on these `Protocol`s, never on concrete teammate packages.
Each is filled by the real module, a fake (`tests/fakes.py`), or nothing (→ the
endpoint returns `module_not_wired`, 501; a run returns `RunOutcome.error`).

| Port | Owner | Signature |
|---|---|---|
| `SeedSource` | Sahil | `build_seed() -> NetworkState` |
| `NetworkModel` | Sahil | `recompute_status(state) -> list[Mutation]`; `resolve_path(service_id, state, *, avoid_nodes, avoid_edges, new_host) -> list[str] | None` |
| `TelemetrySource` | Sahil | `derive(state) -> Telemetry` |
| `FaultInjector` | Sahil | `inject(request, state) -> (Fault, list[Mutation])`; `clear(id, state) -> list[Mutation]`; `active() -> list[Fault]` |
| `Diagnoser` | Yyash | `diagnose(state, telemetry, active_faults) -> Diagnosis` |
| `RecoveryPlanner` | Yyash | `plan(state, diagnosis) -> list[RecoveryPlan]` |
| `DigitalTwin` | Sahil | `validate(state_copy, plan) -> SimulationResult` |
| `SafetyGate` | Hrishi | `evaluate(before, simulation, plan, policy) -> SafetyDecision` |

Composition root: `backend/main.py` builds a `Ports` object and passes it to
`AppContext.build()`. Real modules are wired in one place:

```python
ports = Ports(
    seed_source=RealSeed(), network_model=RealNetworkModel(), telemetry=RealTelemetry(),
    faults=RealFaults(), diagnoser=RealDiagnoser(), planner=RealPlanner(),
    twin=RealTwin(), safety=RealSafety(),
)
app = create_app(ports)
```

---

## 6. Pipeline / orchestration (`backend/pipeline/orchestrator.py`)

Public API:

```
run(auto_apply=True) -> RecoveryRunResult
diagnose() -> Diagnosis
plan() -> (Diagnosis, list[RecoveryPlan])
```

### 6.1 `run()` stages

| # | Stage | On failure |
|---|---|---|
| 1 | `snapshot = state.get_state()` (version V) | — |
| 2 | `telemetry = telemetry.derive(snapshot)` | unwired → `error`; other → `diagnosis_failed` |
| 3 | `diagnosis = diagnoser.diagnose(...)` | exception → `diagnosis_failed` |
| 4 | `plans = planner.plan(...)`; each run through `parse_plan` (schema gate); invalid dropped | unwired → `error`; zero valid → `no_plan` |
| 5 | per plan: `sim = twin.validate(snapshot.model_copy(deep=True), plan)` | exception caught → `sim.feasible = False` (stage isolation) |
| 6 | per plan: `decision = safety.evaluate(snapshot, sim, plan, policy)` | exception caught → reject with `safety_error` violation |
| 7 | `approved = [c for c if c.safety.approved and c.simulation.feasible]` | — |
| 8 | none approved → `no_safe_plan`, stop (no mutation) | — |
| 9 | `best = max(approved, key=(availability, -avg_latency))` | — |
| 10 | `auto_apply` → `executor.apply(best.plan, best.safety)` → version V+1 | conflict/failure → `error`, no mutation |
| 11 | `auto_apply == False` → `approved_pending` | — |

### 6.2 Error policy

- **Expected outcomes are data, HTTP 200.** `no_plan`, `no_safe_plan`,
  `diagnosis_failed`, `approved_pending`, `error`, and per-plan `feasible=false` /
  `approved=false` are all normal `RecoveryRunResult` values.
- **Only an unexpected exception escaping the pipeline** becomes `500
  internal_error` at the `api/` boundary.
- **Stage isolation:** one candidate's twin/safety failure never aborts the run.
- Every stage boundary emits a WS event (§8).

---

## 7. Execution (`backend/execution/`)

`Executor.apply(plan, decision) -> ExecutionResult`. Called only by the pipeline.

Refuses, with `ok=False` and a reason (no mutation) when: `decision.plan_id !=
plan.id`; `not decision.approved`; `plan.based_on_version != current_version`;
`decision.based_on_version != current_version`; an action cannot be translated
(`TranslationError`) — abort before any mutation, never partial.

On success it builds ONE batch — `plan_to_mutations(plan, snapshot, network_model)`
+ `network_model.recompute_status(preview(...))` — and calls
`StateManager.apply_actions()` once.

`translate.py` models only unambiguous structural effects: node/edge `status`,
service `host_node`, and the assigned `path` for reroute/migrate (path from the
`NetworkModel.resolve_path` port). Latency/load/utilisation recomputation is
Sahil's model, not the integration layer's.

---

## 8. REST + WebSocket (`backend/api/`, `backend/events/`)

### 8.1 REST (shapes: `BACKEND_SCHEMA.md` §10; errors: §12)

| Method / path | Purpose | Mutates | Owner of logic |
|---|---|---|---|
| `GET /network/state` | current `NetworkState` | no | Vikash (state) |
| `POST /network/reset` | rebuild seed; `version+1` | yes | Vikash (state) + Sahil (seed) |
| `GET /telemetry` | current `Telemetry` | no | Sahil |
| `GET /faults` | list active faults | no | Sahil |
| `POST /faults` | inject a fault | yes | Sahil (effect) + Vikash (commit + status recompute) |
| `DELETE /faults/{id}` | clear a fault | yes | Sahil (effect) + Vikash (commit) |
| `POST /recovery/diagnose` | diagnosis only | no | Yyash via pipeline |
| `POST /recovery/plan` | diagnosis + candidate plans | no | Yyash via pipeline |
| `POST /recovery/run` | full cycle; applies best approved plan if `auto_apply` | yes iff `outcome == applied` | Vikash (pipeline) |
| `WS /ws` | broadcast state + pipeline events | no | Vikash |

`api/` is transport only — validate request against `models/`, delegate,
serialise. It does **not** import `backend/execution/` (the Executor is owned by
the pipeline). Enforced by `tests/test_architecture_boundaries.py`.

### 8.2 WebSocket

- One `/ws`, broadcast to all connections.
- On connect: one `state` frame (`seq` 0) with the full `NetworkState`.
- Inbound frames read and discarded.
- Envelope + per-type payloads: `BACKEND_SCHEMA.md` §11. Event types: `state`,
  `fault`, `diagnosis`, `simulation`, `safety`, `recovery`, `error`.
- `Broadcaster` (transport-agnostic) owns fan-out; each connection has a bounded
  queue + monotonic `seq`; a slow consumer never blocks the producer.

---

## 9. Dependency rules (enforced by `tests/test_architecture_boundaries.py`)

```
models/       →  (nothing else in backend/)                    [leaf]
state/        →  models
events/       →  models
pipeline/ports→  models, state.mutations                       (NO teammate pkg)
execution/    →  models, state, pipeline.ports
pipeline/     →  models, state, execution, pipeline.ports
api/          →  models, state, pipeline, events               (NOT execution)
main.py       →  api                                           (composition root)

network/ telemetry/ faults/ twin/     →  models  (+ networkx)   [Sahil]
diagnosis/ recovery/                   →  models                [Yyash]
safety/                                →  models                [Hrishi]
frontend/                              →  backend only via REST/WS
```

No lateral imports between teammate packages — data crosses as `models/` types
through the ports.

---

## 10. Determinism

- Seed topology: Sahil's `build_seed` must be seeded / reproducible (same build ⇒ identical topology).
- StateManager, pipeline control flow, schema gate, executor: deterministic.
- Digital Twin and Safety Gate: **must** be deterministic (invariants 6, 7).
- Diagnoser / RecoveryPlanner: deterministic in the MVP (mock). An LLM
  implementation lands later behind the same port; malformed output is caught by
  the schema gate and the run falls back or reports honestly — the pipeline does
  not change.

---

## 11. Testing (Vikash's responsibility)

| Test file | Covers |
|---|---|
| `test_models_contracts.py` | every model: valid instance round-trips JSON; extras rejected; `Z` timestamps |
| `test_models_state.py` | `NetworkState` structural invariants; numeric edge-id order; `ServiceState.path` rules |
| `test_models_recovery.py` | closed action vocabulary; plan bounds |
| `test_schema_validation.py` | the AI-output schema gate (malformed / OOV / unknown id / version mismatch) |
| `test_state_manager.py` | version monotonicity, deep-copy isolation, atomic reject, subscriber isolation |
| `test_broadcaster.py` | per-connection `seq`, fan-out, slow-consumer isolation |
| `test_api_contract.py` | endpoint shapes, status codes, `module_not_wired` (501) |
| `test_ws_contract.py` | initial `state` frame, broadcast on mutation, inbound ignored |
| `test_pipeline_sequencing.py` | stage order + WS events; every `RunOutcome` branch |
| `test_safety_boundary.py` | Executor refuses unapproved / mismatched / stale plans; approved plan applies once |
| `test_architecture_boundaries.py` | the §9 import rules; teammate placeholders hold no Vikash code |
| `test_e2e_pipeline.py` | fault → state/telemetry change → run → recovered, over HTTP, with fakes; assigned-path semantics |

Teammate suites (seed/telemetry/fault math, twin isolation/determinism, planner
output validity, safety golden tests) are owned by the respective person.
