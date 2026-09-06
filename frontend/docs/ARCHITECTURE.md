# AEGIS — Architecture

**Owner:** Vikash (System Architecture + Integration Lead)
**Status:** Draft for team ratification
**Scope:** 3-day hackathon MVP — modular monolith, no external infrastructure.

This is the authoritative architecture document. `BACKEND_SCHEMA.md` is the
authoritative field-level contract. Where the two overlap, this document defines
*boundaries and rules*; `BACKEND_SCHEMA.md` defines *shapes*.

---

## 1. System overview

AEGIS is a simulated, safety-gated autonomous network-recovery engine.

```
Seed topology
    │
    ▼
NetworkState  ◄────────────── single source of truth (owned by StateManager)
    │
    ├──► Telemetry (derived, read-only projection)
    │
Fault injected ──► StateManager mutates NetworkState (version++)
    │
    ▼
Recovery pipeline run:
    NetworkState snapshot (deep copy)
        │
        ▼
    AI Diagnosis ............ advisory data only
        │
        ▼
    AI Recovery Planner ..... candidate RecoveryPlans (closed action schema)
        │
        ▼
    Schema Validation ....... drop malformed / out-of-vocabulary plans
        │
        ▼
    Digital Twin ............ simulate each plan on an isolated copy → SimulationResult
        │
        ▼
    Safety Engine ........... deterministic approve / reject per plan → SafetyDecision
        │
        ▼
    Pipeline picks best safety-approved plan
        │
        ▼
    Execution .............. applies ONLY the approved plan via StateManager (version++)
        │
        ▼
    Updated NetworkState ──► broadcast over WebSocket
```

**Authority chain:** AI advises → Digital Twin provides evidence → Safety Engine
decides → Execution applies → StateManager mutates. No shortcuts.

---

## 2. Architectural invariants (non-negotiable)

These are frozen. Any change requires all four owners to agree.

1. **`NetworkState` is the single source of truth** for the entire application.
2. **`StateManager` is the only component that may mutate live `NetworkState`.**
3. **AI output never directly touches the network** — it produces data that
   downstream components choose to act on.
4. **AI output must conform to a closed `RecoveryAction` schema.** No free-form
   strings, shell commands, router configs, code, or SQL.
5. **AI cannot invoke Execution.** The `ai/` module may not import `execution/`,
   `state/`, `twin/`, or `safety/`.
6. **The Digital Twin operates on an isolated deep copy of state.**
7. **The Digital Twin cannot mutate live `NetworkState`.** `twin/` may not import
   `state/` or `execution/`.
8. **The Safety Engine is deterministic** — same inputs always produce the same
   `SafetyDecision`.
9. **The Safety Engine is independent of AI reasoning.** `safety/` may not import
   `ai/`. It consumes only structured data (`NetworkState`, `SimulationResult`,
   `RecoveryPlan`, policy config).
10. **Execution applies only safety-approved plans.** A plan without an
    `approved == true` `SafetyDecision` for the current state version is never
    applied.
11. **No second state store may emerge** in the frontend or backend. The frontend
    renders server-provided `NetworkState`; it does not maintain an authoritative
    parallel model.
12. **WebSocket is observation-only.** It broadcasts state and events. It is never
    an alternative mutation path. Inbound WS messages are ignored.
13. **No arbitrary executable commands** may be produced, stored, or executed
    anywhere in the recovery path.
14. **The architecture stays hackathon-appropriate:** one process, one worker,
    in-memory state, one seed topology, no databases, no queues, no orchestrators.

---

## 3. Module boundaries

Modular monolith. One FastAPI process. Package layout under `backend/`:

| Module | Responsibility | Owner |
|---|---|---|
| `models/` | Canonical shared pydantic contracts. **Leaf module** — imports nothing else internal. | Vikash |
| `state/` | `StateManager`: owns the one live `NetworkState`; only writer; version + subscriber notification. | Vikash |
| `network/` | Seed topology builder; `NetworkState ↔ graph` helpers for algorithms. | Sahil |
| `telemetry/` | Pure projection `NetworkState → Telemetry`. | Sahil |
| `faults/` | `FaultInjector`: validate a `Fault`, compute its effect, apply via `StateManager`, track active faults. | Sahil |
| `twin/` | Digital Twin: deep-copy state, apply one `RecoveryPlan`, produce `SimulationResult`. | Sahil |
| `ai/` | Diagnosis + Recovery Planner + LLM client + deterministic fallback. Returns data only. | Yyash |
| `safety/` | Safety Engine: deterministic `evaluate()` → `SafetyDecision`. | Hrishi |
| `execution/` | Apply an approved `RecoveryPlan` via `StateManager`. | Vikash |
| `pipeline.py` | Orchestrator. The only module that wires the flow together. | Vikash |
| `api/` | REST routes + `/ws` WebSocket. Transport only. | Vikash |
| `main.py` | App assembly. | Vikash |
| `frontend/` | Renders state + events, issues commands over REST. | Hrishi |

### 3.1 Boundary rules per module

- **`models/`** — contains schemas and validation only. No behavior, no I/O, no
  business logic. Every other module imports its types from here and **nowhere
  else re-defines a canonical model**.
- **`state/`** — exposes `snapshot()` (returns a deep copy) and `apply_actions()`
  (the single mutation entry point). Everyone reads through copies; only
  `faults/` and `execution/` call the mutator.
- **`network/`** — provides `build_seed() -> NetworkState` and conversion helpers.
  It does **not** hold authoritative state.
- **`telemetry/`** — a pure function. No mutation, no persistence, no side effects.
- **`faults/`** — the only translation of operator fault requests into state
  changes. Applies exclusively through `StateManager`.
- **`twin/`** — a pure function `simulate(state_copy, plan) -> SimulationResult`.
  Receives a `NetworkState`, never a `StateManager`. No import of `state/`.
- **`ai/`** — pure advisory. Input: read-only state copy + telemetry + active
  faults (+ diagnosis for planning). Output: `Diagnosis` / `list[RecoveryPlan]`.
  No import of `state/`, `execution/`, `twin/`, `safety/`.
- **`safety/`** — pure deterministic function. No import of `ai/`. No network
  calls. No randomness. No wall-clock branching.
- **`execution/`** — the only caller of `StateManager.apply_actions()` for
  recovery. Called only by `pipeline.py`, only after safety approval.
- **`pipeline.py`** — owns all control flow and error handling for a recovery run.
  Delegates every domain decision to the owning module.
- **`api/`** — request/response validation and transport. No domain logic, no
  graph algorithms, no LLM calls.

---

## 4. Canonical state & StateManager

### 4.1 NetworkState

Defined in `BACKEND_SCHEMA.md §2`. Key properties:

- Carries `version: int` (monotonic, starts at 0) and `updated_at: datetime`.
- Contains all `NodeState`, `EdgeState`, `ServiceState`, and `active_fault_ids`.
- Is a value object: consumers receive **deep copies**, never the live reference.

### 4.2 StateManager (`state/`)

The single authority over live state.

```
class StateManager:
    def get_state() -> NetworkState          # deep copy of live state (alias: snapshot)
    def apply_actions(mutations, reason) -> NetworkState
    def reset(seed: NetworkState) -> NetworkState   # caller supplies the seed
    def subscribe(callback)                  # WS layer registers here
    def current_version() -> int
```

`reset()` takes the seed as an argument so `state/` stays decoupled from the seed
source. The composition root (`api/context.py` today, `main.py` once
`network.build_seed` exists) owns which factory is passed.

Rules:

- `snapshot()` returns `live.model_copy(deep=True)`. No caller ever holds the
  live object.
- `apply_actions()` is the **only** mutation path. It:
  1. builds the next `NetworkState` from the current one + mutations,
  2. validates structural invariants (every edge endpoint exists, every service
     host exists, ids well-formed),
  3. increments `version` by exactly 1, sets `updated_at`,
  4. swaps the live reference atomically,
  5. notifies subscribers (WS broadcast).
  On validation failure it raises and leaves the live state untouched.
- Callers of `apply_actions()`: **`faults/` and `execution/` only.** Enforced by
  the import-lint test (§9).
- `version` is **never reset**, including on `POST /network/reset` — reset is a
  normal mutation producing `version + 1`. This keeps the frontend's
  stale-frame rule (drop frames with `version <= current`) always correct.
- No locking. Single worker, single asyncio event loop.
  <!-- ponytail: single-writer relies on one worker + GIL; add asyncio.Lock only if we ever run multiple workers, which the MVP will not -->
- A subscriber that raises is isolated: the mutation still commits, the other
  subscribers still fire, and `apply_actions()` still returns normally.

### 4.3 Mutation primitives (`state/mutations.py`) — the write contract

`apply_actions()` does not take `RecoveryAction`s or fault objects. It takes a
list of **mechanical field-write primitives** with no domain semantics:

| primitive | effect |
|---|---|
| `SetNodeFields(node_id, fields)` | merge `fields` into that node |
| `SetEdgeFields(edge_id, fields)` | merge `fields` into that edge |
| `SetServiceFields(service_id, fields)` | merge `fields` into that service |
| `SetActiveFaults(fault_ids)` | replace `active_fault_ids` |

Unknown target id → rejected. Unknown/invalid field → rejected by the full
re-validation. The batch is all-or-nothing.

- **`faults/` (Sahil)** translates a `Fault` + its params into these primitives.
- **`execution/` (Vikash)** translates an approved `RecoveryPlan`'s actions into
  these primitives.

"Which fields, what values" is the caller's domain logic; "apply atomically and
re-validate" is `StateManager`'s. This shape is a shared contract
(`BACKEND_SCHEMA.md` §12).

---

## 5. Recovery pipeline / orchestration

`pipeline.py` exposes:

```
run(auto_apply: bool = True) -> RecoveryRunResult
diagnose() -> Diagnosis
plan(diagnosis_id: str | None = None) -> tuple[Diagnosis, list[RecoveryPlan]]
```

### 5.1 `run()` stages

| # | Stage | Module | On failure |
|---|---|---|---|
| 1 | `snapshot = StateManager.snapshot()` | `state/` | — |
| 2 | `telemetry = telemetry.derive(snapshot)` | `telemetry/` | bug → 500 |
| 3 | `diagnosis = ai.diagnose(snapshot, faults, telemetry)` | `ai/` | retry once → heuristic fallback → else `outcome = diagnosis_failed`, stop |
| 4 | `plans = ai.plan(snapshot, diagnosis)`; each parsed by schema validation; invalid dropped | `ai/` + `models/` | zero valid → heuristic planner → still zero → `outcome = no_plan`, stop |
| 5 | per plan: `sim = twin.simulate(snapshot.model_copy(deep=True), plan)` | `twin/` | exception caught → `sim.feasible = False` |
| 6 | per plan: `safety = safety.evaluate(snapshot, sim, plan, policy)` | `safety/` | exception caught → treated as reject w/ `safety_error` violation |
| 7 | `approved = [c for c if c.safety.approved and c.simulation.feasible]` | `pipeline` | — |
| 8 | none approved → `outcome = no_safe_plan`, stop (no mutation) | `pipeline` | — |
| 9 | `best = max(approved, key=(availability, -avg_latency))` | `pipeline` | — |
| 10 | `auto_apply` → `execution.apply(best.plan)` → version++ → WS `state` | `execution/` | conflict/failure → `outcome = error`, no mutation |
| 11 | `auto_apply == False` → `outcome = approved_pending` | `pipeline` | — |

### 5.2 Error-propagation policy

- **Expected outcomes are data, not exceptions.** `no_plan`, `no_safe_plan`,
  `diagnosis_failed`, `approved_pending`, and per-plan `feasible=false` /
  `approved=false` are all normal `RecoveryRunResult` values with HTTP 200.
- **Only infrastructure faults / bugs raise.** These are caught at the `api/`
  boundary and returned as the error schema (`BACKEND_SCHEMA.md §9`) with HTTP
  500.
- **Stage isolation:** one candidate plan's twin or safety failure never aborts
  the run; remaining candidates are still evaluated.
- Every stage transition emits a WebSocket event (§7).

---

## 6. REST boundary

Full contract in `API_CONTRACT` section of `TRD.md` and shapes in
`BACKEND_SCHEMA.md §8`. Boundary rules:

- REST is the **only** mutation channel.
- Mutating endpoints: `POST /network/reset`, `POST /faults`, `DELETE /faults/{id}`,
  `POST /recovery/run` (iff a plan is applied). All others are reads.
- `api/` performs schema validation of the request, delegates to the owning
  module, and serializes the response. It contains no domain logic.
- Endpoint → owning module:

  | Endpoint | Implementation owner |
  |---|---|
  | `GET /network/state` | `state/` (Vikash) |
  | `POST /network/reset` | `state/` + `network/` seed (Vikash + Sahil) |
  | `GET /telemetry` | `telemetry/` (Sahil) |
  | `GET /faults`, `POST /faults`, `DELETE /faults/{id}` | `faults/` (Sahil) |
  | `POST /recovery/diagnose` | `ai/` via `pipeline` (Yyash + Vikash) |
  | `POST /recovery/plan` | `ai/` via `pipeline` (Yyash + Vikash) |
  | `POST /recovery/run` | `pipeline` (Vikash) orchestrating all |
  | `WS /ws` | `api/` + `state/` subscription (Vikash) |

---

## 7. WebSocket boundary

- **Broadcast-oriented.** One `/ws` endpoint. All connected clients receive the
  same event stream.
- **On connect:** server immediately sends one `state` event with the current
  full `NetworkState`, then streams subsequent events.
- **Inbound messages are ignored.** The WS layer never mutates state and never
  triggers pipeline runs. (Invariant 12.)
- **Event envelope** and per-type payloads: `BACKEND_SCHEMA.md §7`.
- Event types: `state`, `fault`, `diagnosis`, `simulation`, `safety`,
  `recovery`, `error`.
- The WS layer is a **subscriber** of `StateManager` plus a sink the `pipeline`
  publishes progress events to. It holds no state of its own beyond the
  connection set and a per-connection sequence counter.

---

## 8. Dependency direction

`may import →`

```
models/        →  (nothing internal)                         [leaf]

config.py      →  models
network/       →  models
telemetry/     →  models, network
faults/        →  models, state, network
state/         →  models
ai/            →  models
twin/          →  models, network
safety/        →  models
execution/     →  models, state, network
pipeline.py    →  models, state, telemetry, faults, ai, twin, safety, execution
api/           →  models, state, pipeline, config
main.py        →  api
frontend/      →  (backend only via services/api.ts + services/socket.ts)
```

- `models/` is a strict **leaf**. `pipeline.py` is the strict **root**.
- No lateral imports between sibling domain modules.
- **`api/` does not import `execution/`.** The `Executor` is constructed and
  owned by `pipeline.py` (the only caller of execution — invariant 10). This is
  enforced by `tests/test_architecture_imports.py::test_only_pipeline_imports_execution`.

### 8.1 Forbidden dependencies (enforced by test — §9)

| Forbidden | Reason (invariant) |
|---|---|
| `ai/` → `state/`, `execution/`, `twin/`, `safety/` | 3, 5 |
| `twin/` → `state/`, `execution/` | 6, 7 |
| `safety/` → `ai/`, `twin/`, `network/`, `state/` | 8, 9 |
| anything except `pipeline.py` → `execution/` | 10 |
| any module except `models/` defining a canonical schema | 1, 11 |
| any mutation of `NetworkState` outside `StateManager.apply_actions()` | 2 |
| `frontend/` containing recovery / safety / diagnosis logic | 11 |
| any inbound-WS code path reaching `StateManager` or `pipeline` | 12 |

---

## 9. Testing boundaries

| Layer | Owner | What it covers |
|---|---|---|
| `models/` contract fixtures (`tests/contracts/`) | Vikash | one canonical valid instance + invalid variants of every model; imported by everyone's tests |
| `StateManager` unit | Vikash | version monotonicity, deep-copy isolation, invariant enforcement, subscriber notification |
| Import-lint | Vikash | forbidden dependency table (§8.1) fails CI if violated |
| `pipeline` integration | Vikash | full flow with fake AI / twin / safety; all outcome branches |
| API contract | Vikash | every endpoint's request/response/error shape |
| WebSocket | Vikash | connect → initial `state`; version bump → broadcast; inbound ignored |
| E2E | Vikash | `POST /faults` → `POST /recovery/run` → `GET /network/state`: availability recovers, events ordered |
| Seed + fault + telemetry | Sahil | seed validity, fault effect, telemetry math |
| Twin isolation | Sahil (harness by Vikash) | `StateManager.version` unchanged after `simulate()`; same input → identical `SimulationResult` |
| AI output validation | Yyash | malformed-output fixtures, schema conformance, fallback path |
| Safety | Hrishi | per-rule golden tests; determinism (same input ×100 → identical decision) |

Contract fixtures are the shared integration currency: if a fixture changes, the
owning conversation happens before code merges.

---

## 10. Teammate module boundaries (architectural only)

The following are **contracts and boundaries**, not implementation instructions.
Internal algorithms, data structures, and design are owned by the named person.

### 10.1 Network simulation / topology / telemetry / fault injection / Digital Twin — Sahil

- **`network.build_seed() -> NetworkState`** — returns a valid `NetworkState` at
  `version = 0`: connected graph, ≥5 nodes all `healthy`, all edges `active`,
  ≥3 `ServiceState` entries hosted on existing nodes, `active_fault_ids = []`.
- **`telemetry.derive(state: NetworkState) -> Telemetry`** — pure function,
  no side effects, output conforms to `BACKEND_SCHEMA.md §3`.
- **`FaultInjector`** — validates a `Fault` request against the current state,
  computes the resulting field mutations, applies them **through
  `StateManager.apply_actions()`**, and maintains the active-fault set.
  `DELETE /faults/{id}` restores affected elements toward nominal.
- **`twin.simulate(state_copy: NetworkState, plan: RecoveryPlan) ->
  SimulationResult`** — pure function on the passed copy; must never import or
  reference `StateManager`; output conforms to `BACKEND_SCHEMA.md §6`.
- Boundary: the twin receives a `NetworkState` value and returns a
  `SimulationResult` value. Nothing else crosses.

### 10.2 AI diagnosis / recovery planning / structured output — Yyash

- **`ai.diagnose(state, active_faults, telemetry) -> Diagnosis`** — advisory.
  Output conforms to `BACKEND_SCHEMA.md §4`.
- **`ai.plan(state, diagnosis) -> list[RecoveryPlan]`** — each plan uses only the
  closed `RecoveryAction` vocabulary (`BACKEND_SCHEMA.md §5`), ≤6 actions,
  schema-valid, `based_on_version` set to the input state's version.
- Malformed LLM output must be handled inside `ai/` (retry + deterministic
  fallback). The pipeline receives either valid typed data or an explicit
  failure signal — never partial or malformed structures.
- Boundary: `ai/` imports `models/` only. It returns data. It has no reference to
  state mutation, execution, the twin, or safety.

### 10.3 Safety Engine — Hrishi

- **`safety.evaluate(before: NetworkState, sim: SimulationResult,
  plan: RecoveryPlan, policy: PolicyConfig) -> SafetyDecision`** — deterministic
  pure function. Output conforms to `BACKEND_SCHEMA.md §6`.
- A plan is `approved` iff it produces **no `critical` violations**.
- `safety/` imports `models/` only. No `ai/`, no randomness, no I/O.
- Policy thresholds live in one config object; their values are **TEAM DECISION
  REQUIRED** (see `IMPLEMENTATION_PLAN.md`).

### 10.4 Frontend — Hrishi

- Consumes `GET /network/state`, `GET /telemetry`, `GET /faults` and the `/ws`
  event stream. Issues commands via the mutating REST endpoints.
- Maintains a single client-side view model sourced entirely from the server.
  It is **not** an authoritative state store (invariant 11).
- Visual design, component architecture, interaction, styling, and motion are
  owned by Hrishi. See `UI_UX_BRIEF.md`.

---

## 11. Current state vs target state

| Concern | Current (`feature/architecture` @ HEAD) | Target |
|---|---|---|
| Source of truth | `NetworkSimulator`'s `networkx.Graph` (in `backend/network/simulator.py`) | Canonical `NetworkState` owned by `StateManager` |
| `NetworkState` model | `nodes: dict`, `edges: list` only | + `version`, `updated_at`, `services`, `active_fault_ids`; nodes gain `capacity`/`load`; edges gain `id`/`utilization` |
| State ownership | module-level `sim = NetworkSimulator()` singleton in `api/routes.py` | `StateManager` injected; `api/` never owns state |
| Fault API | `POST /network/fault/kill-node/{id}`, `POST /network/fault/restart-node/{id}` | `POST /faults`, `DELETE /faults/{id}` (generic) |
| Pipeline / AI / twin / safety / execution | none | as specified |
| WebSocket | none | `/ws` broadcast |
| Telemetry | none | `telemetry.derive()` + `GET /telemetry` |
| Frontend state | hardcoded, own 5-node topology (`origin/frontend`) | consumes live `NetworkState` |
| Repo hygiene | `__pycache__` committed, no `.gitignore`, no `requirements.txt`, Python 3.11 bytecode vs 3.14 system | see `IMPLEMENTATION_PLAN.md` Phase 0 |

Application code is **not** modified by this documentation pass. Items touching
teammate-owned modules are raised as `INFORM` notes in `IMPLEMENTATION_PLAN.md`.

---

## 12. Explicit non-goals

Kubernetes · Kafka · Redis · PostgreSQL / any database · cloud infrastructure ·
real network hardware · real SDN controllers · RL training · custom neural
networks · microservices · auth / users / sessions · persistence (restart =
fresh seed) · topology editor · historical time-series storage · real routing
protocols (BGP/OSPF) · plan-space solvers (ILP/A*) · multi-step lookahead ·
streaming LLM output · agent frameworks · WS command channel · client-side
reconciliation · Docker for development · config service / feature flags ·
transaction log beyond a single pre-execution snapshot.
