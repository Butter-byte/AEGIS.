# AEGIS — Technical Requirements Document (TRD)

**Owner:** Vikash (System Architecture + Integration Lead)
**Companion docs:** `ARCHITECTURE.md` (boundaries & invariants),
`BACKEND_SCHEMA.md` (field-level contracts), `APP_FLOW.md` (flows).

This TRD fully specifies the architecture and integration layer (Vikash's
responsibility). For teammate-owned systems it specifies **responsibility, input
contract, output contract, and integration boundary only** — not internal design.

---

## 1. Technical goals & constraints

| # | Requirement |
|---|---|
| T1 | One FastAPI process, one worker (`uvicorn --workers 1`), in-memory state. |
| T2 | Python 3.11, Pydantic v2, FastAPI, `networkx`. Frontend: Vite + React + `@xyflow/react`. |
| T3 | No database, no message queue, no cache server, no container runtime for dev. |
| T4 | State is not persisted. Process restart = fresh seed topology. |
| T5 | All shared data crossing a module boundary conforms to `BACKEND_SCHEMA.md`. |
| T6 | The 14 architectural invariants in `ARCHITECTURE.md §2` hold at all times. |
| T7 | A full recovery run completes in < 5 s with the deterministic fallback planner (LLM latency excluded). |
| T8 | The system is demoable end-to-end without any live LLM call. |

---

## 2. Architecture & integration layer — FULLY SPECIFIED (Vikash)

### 2.1 Canonical models (`backend/models/`)

- Single source of every shared schema. Leaf module — imports nothing internal.
- Contains: the 11 canonical models, the `RecoveryAction` discriminated union,
  request/response models, WS envelope + payload models, error model, enums.
- Provides `SchemaValidation` helpers:
  - `parse_diagnosis(raw: dict) -> Diagnosis` (raises `SchemaError` on failure)
  - `parse_plan(raw: dict, source_state: NetworkState) -> RecoveryPlan`
    (validates closed vocabulary + referenced-id existence)
- No behavior beyond parsing/validation. No I/O.

### 2.2 StateManager (`backend/state/`)

Specified in `ARCHITECTURE.md §4.2`. Requirements:

| # | Requirement |
|---|---|
| S1 | Holds exactly one live `NetworkState`. Initialized from `network.build_seed()` at startup. |
| S2 | `snapshot()` returns `live.model_copy(deep=True)`. No caller receives the live object. |
| S3 | `apply_actions(mutations, reason)` is the **only** mutation entry point. |
| S4 | Each `apply_actions` call: builds next state → validates structural invariants (`BACKEND_SCHEMA.md §2`) → `version += 1` → sets `updated_at` → swaps atomically → notifies subscribers. |
| S5 | On validation failure: raise `StateInvariantError`, live state unchanged. |
| S6 | Callers of the mutator: `faults/` and `execution/` only (enforced by import-lint). |
| S7 | `version` is never reset. `reset()` is a normal mutation to `version + 1`. |
| S8 | `subscribe(cb)` registers a callback invoked with the new `NetworkState` after every mutation; used by the WS layer. |
| S9 | No locking (single worker). Documented ceiling; upgrade path = `asyncio.Lock`. |

### 2.3 Pipeline / orchestration (`backend/pipeline.py`)

- Public API: `run(auto_apply=True) -> RecoveryRunResult`,
  `diagnose() -> Diagnosis`, `plan(diagnosis_id=None) -> (Diagnosis, list[RecoveryPlan])`.
- Stage sequence, fallback rules, and outcome mapping: `ARCHITECTURE.md §5`.
- Owns all control flow and error handling for a recovery run. Delegates every
  domain decision to the owning module.
- Publishes a WS event at each stage boundary (`diagnosis`, `simulation`,
  `safety`, `recovery`).
- Guarantees:
  - never calls `execution/` unless a candidate has `safety.approved == true`
    **and** `simulation.feasible == true` for the current `version`;
  - re-checks `plan.based_on_version == StateManager.current_version()` before
    execution; mismatch → `outcome = error`, `code = conflict`, no mutation;
  - stage isolation — one plan's failure never aborts evaluation of the others.

### 2.4 Execution (`backend/execution/`)

| # | Requirement |
|---|---|
| E1 | `apply(plan: RecoveryPlan) -> ExecutionResult`. Called only by `pipeline.py`. |
| E2 | Precondition (asserted): caller has verified an approved `SafetyDecision` for `plan` at the current `version`. |
| E3 | Re-verifies `plan.based_on_version == StateManager.current_version()`; mismatch → `ExecutionResult(ok=False, reason="conflict")`, no mutation. |
| E4 | Translates the ordered `actions` into one batch of field mutations and calls `StateManager.apply_actions(batch, reason=f"recovery {plan.id}")` **once** (single `version` bump, atomic). |
| E5 | If any action cannot be translated to concrete mutations → abort before calling the mutator; `ExecutionResult(ok=False)`; no partial application. |
| E6 | `execution/` is imported by `pipeline.py` and nothing else. |

`ExecutionResult = { ok: bool, resulting_version: int | null, reason: str | null }`

> The *effect* of each action type on state fields is teammate-internal (Sahil,
> shared with the twin). Execution and the twin must apply identical semantics —
> see INFORM Sahil in `IMPLEMENTATION_PLAN.md`.

### 2.5 REST layer (`backend/api/`)

- Transport only: validate request against `models/`, delegate, serialize.
- No domain logic, no graph algorithms, no LLM calls, no state ownership.
- Endpoint contracts: §5 below.
- Maps exceptions to the error schema (`BACKEND_SCHEMA.md §9`).

### 2.6 WebSocket layer (`backend/api/ws.py`)

- One `/ws` endpoint, broadcast to all connections.
- On connect: send one `state` event with the current `NetworkState`.
- Subscribes to `StateManager`; emits a `state` event on every mutation.
- Provides a `publish(event)` sink the pipeline uses for progress events.
- Inbound frames: read and discarded. Never reaches `StateManager` or `pipeline`.
- Holds only: the connection set + a per-connection `seq` counter.

### 2.7 Repository & integration conventions (Vikash)

| # | Convention |
|---|---|
| R1 | Python 3.11 pinned. `backend/requirements.txt` with pinned versions. |
| R2 | `.gitignore` excludes `__pycache__/`, `*.pyc`, `.venv/`, `node_modules/`, `dist/`, `.env`. |
| R3 | Committed bytecode (`backend/**/__pycache__/*.pyc`) removed from the index. |
| R4 | Branch model: `main` always demoable; one short-lived branch per owner (`feat/<area>`); integrate via PR. |
| R5 | `backend/config.py` holds the only tunables: seed params, safety thresholds, LLM settings. |
| R6 | Frontend talks to the backend only through `frontend/services/api.ts` and `frontend/services/socket.ts`. |
| R7 | Shared contract fixtures live in `tests/contracts/` (Vikash-owned); all modules' tests import them. |

> R1–R3 concern files currently committed by Sahil's initial work — see
> INFORM Sahil in `IMPLEMENTATION_PLAN.md`. This pass documents the target; it
> does not modify code.

---

## 3. Teammate-owned systems — RESPONSIBILITY / INPUT / OUTPUT / BOUNDARY ONLY

### 3.1 Network simulation, topology, telemetry, fault injection — Sahil

| Aspect | Contract |
|---|---|
| Responsibility | Build and evolve the simulated network; derive telemetry; apply operator faults. |
| Input | `NetworkState` (read copy) for telemetry; `FaultRequest` for injection; fault `id` for clearing. |
| Output | `NetworkState` field mutations (applied via `StateManager`); `Telemetry` value; active `Fault` list. |
| Boundary | Fault effects reach state **only** through `StateManager.apply_actions()`. Telemetry is a pure function. No direct writes to `NetworkState`. |
| Provides to integration | `network.build_seed() -> NetworkState`; `telemetry.derive(state) -> Telemetry`; `FaultInjector` with `inject(req) -> (Fault, mutations)`, `clear(id) -> mutations`, `active() -> list[Fault]`. |

Internal (not specified here): topology structure, path algorithms, latency/load
model, availability formula, fault → field mapping.

### 3.2 Digital Twin — Sahil

| Aspect | Contract |
|---|---|
| Responsibility | Evaluate a candidate `RecoveryPlan` against an isolated copy of state. |
| Input | `NetworkState` (deep copy, passed by value) + one `RecoveryPlan`. |
| Output | `SimulationResult` (`BACKEND_SCHEMA.md §6.1`). |
| Boundary | `twin/` imports `models/` and `network/` only. **Never** imports `state/` or `execution/`. Must not mutate anything reachable from `StateManager`. |
| Invariant test (Vikash provides harness) | `StateManager.version` unchanged after `simulate()`; identical input → identical output. |

Internal: simulation method, how each `ActionType` transforms the copy, metric
computation.

### 3.3 AI diagnosis & recovery planning — Yyash

| Aspect | Contract |
|---|---|
| Responsibility | Diagnose failures; propose candidate recovery plans. |
| Input | `NetworkState` (read copy), active `Fault` list, `Telemetry`; plus `Diagnosis` for planning. |
| Output | `Diagnosis` (`§4`); `list[RecoveryPlan]` using the closed `RecoveryAction` vocabulary (`§5`), ≤6 actions each, `based_on_version` set. |
| Boundary | `ai/` imports `models/` only. Returns data. No reference to `state/`, `execution/`, `twin/`, `safety/`. Cannot trigger a run or an apply. |
| Failure handling | Malformed/exception handled inside `ai/` (retry once, then deterministic fallback). Pipeline receives valid typed data or an explicit failure signal — never malformed structures. |
| Provides to integration | `ai.diagnose(state, faults, telemetry) -> Diagnosis`; `ai.plan(state, diagnosis) -> list[RecoveryPlan]`; a `source="heuristic"` fallback for both. |

Internal: prompts, model choice, structured-output mechanism, suspicion logic,
candidate strategy, fallback heuristics.

### 3.4 Safety Engine — Hrishi

| Aspect | Contract |
|---|---|
| Responsibility | Deterministically approve or reject each candidate plan. |
| Input | `before: NetworkState`, `sim: SimulationResult`, `plan: RecoveryPlan`, `policy: PolicyConfig`. |
| Output | `SafetyDecision` (`§6.2`). `approved` iff no `critical` violations. |
| Boundary | `safety/` imports `models/` only. No `ai/`, no I/O, no randomness, no wall-clock branching. Same inputs → same output, always. |
| Provides to integration | `safety.evaluate(before, sim, plan, policy) -> SafetyDecision`; the set of rule ids it can emit; `PolicyConfig` default (values pending team decision). |

Internal: rule implementations, evaluation order, message wording.

### 3.5 Frontend — Hrishi

See `UI_UX_BRIEF.md`. Integration contract:

| Aspect | Contract |
|---|---|
| Consumes | `GET /network/state`, `GET /telemetry`, `GET /faults`, `/ws` events. |
| Commands | `POST /faults`, `DELETE /faults/{id}`, `POST /network/reset`, `POST /recovery/diagnose`, `POST /recovery/plan`, `POST /recovery/run`. |
| State rule | Single client-side view model sourced entirely from the server. Not an authoritative store (invariant 11). Drops `state` frames with `version <= current`. |
| Boundary | No recovery / safety / diagnosis logic in the frontend. Display and command only. |

Internal: everything visual — components, layout, styling, motion, interaction.

---

## 4. Data flow (integration view)

```
                    ┌─────────────┐
  REST commands ───►│   api/      │───► pipeline.py ──┬─► ai/        (data)
                    │ (transport) │                   ├─► twin/      (copy in → result out)
  REST reads    ───►│             │◄─── StateManager  ├─► safety/    (data in → decision out)
                    └──────┬──────┘        ▲          └─► execution/ ─► StateManager.apply_actions()
                           │               │                                    │
                    ┌──────▼──────┐        │ snapshot()/subscribe()             │ version++
                    │   ws.py     │◄───────┴────────────────────────────────────┘
                    │ (broadcast) │───► all clients: state + pipeline events
                    └─────────────┘
  faults/ ──► StateManager.apply_actions()  (the other mutator)
```

Mutation entry points into `NetworkState`: **`faults/`** and **`execution/`**,
both via `StateManager.apply_actions()`. Nothing else.

---

## 5. API contract (target)

Shapes: `BACKEND_SCHEMA.md §8`. Error behavior: `BACKEND_SCHEMA.md §9`.

| Method / path | Purpose | Reads/Mutates | Validation | Error behavior | Implementation owner |
|---|---|---|---|---|---|
| `GET /network/state` | Return current canonical `NetworkState` | reads | none | always 200 | `state/` (Vikash) |
| `POST /network/reset` | Rebuild seed, clear faults; emits `version+1` | mutates | none | always 200 | `state/` + seed (Vikash + Sahil) |
| `GET /telemetry` | Current derived `Telemetry` | reads | none | 200 | `telemetry/` (Sahil) |
| `GET /faults` | List active faults | reads | none | 200 | `faults/` (Sahil) |
| `POST /faults` | Inject a fault | mutates | `type` ∈ enum; `target` exists & correct kind; `params` keys valid for `type` | 422 `validation_error`/`invalid_fault`; 404 `invalid_target` | `faults/` (Sahil), commit via `state/` |
| `DELETE /faults/{id}` | Clear a fault, restore affected elements | mutates | `id` is an active fault | 404 `not_found` | `faults/` (Sahil), commit via `state/` |
| `POST /recovery/diagnose` | Run diagnosis only | reads | none | 200 (fallback covers AI failure); 502 `pipeline_error` only if fallback also fails | `ai/` via `pipeline` |
| `POST /recovery/plan` | Diagnosis + candidate plans, no simulation | reads | optional `diagnosis_id` must exist | 200 with possibly-empty `candidates`; 502 `pipeline_error` on total AI failure | `ai/` via `pipeline` |
| `POST /recovery/run` | Full pipeline; auto-applies best approved plan if `auto_apply` | mutates iff `outcome == applied` | optional `auto_apply` bool | 200 with `outcome`; 500 `execution_error`/`internal_error` only on bug | `pipeline` (Vikash) |
| `WS /ws` | Broadcast state + pipeline events | reads (broadcast) | inbound ignored | connection close on transport error | `api/` + `state/` (Vikash) |

---

## 6. Non-functional requirements

| # | Requirement |
|---|---|
| N1 | A recovery run with the fallback planner returns in < 5 s. |
| N2 | `GET /network/state` and `GET /telemetry` return in < 100 ms for the seed-scale topology (≤ ~30 nodes). |
| N3 | WS `state` broadcast latency after a mutation < 250 ms. |
| N4 | The system starts with `uvicorn backend.main:app` and one command for the frontend (`npm run dev`). |
| N5 | No secret is committed; LLM key via `.env` (git-ignored). |
| N6 | Deterministic components (StateManager, pipeline control flow, safety, twin) are reproducible across runs. |

---

## 7. Integration & E2E strategy (Vikash)

| Test | Scope | Pass criterion |
|---|---|---|
| Contract fixtures | every model in `tests/contracts/` | valid instance parses; invalid variants rejected |
| Import-lint | forbidden-dependency table (`ARCHITECTURE.md §8.1`) | zero violations |
| StateManager unit | mutation, versioning, isolation, invariants | S1–S9 hold |
| Pipeline integration | fakes for `ai`/`twin`/`safety` | every `RunOutcome` branch reachable and correct; no mutation on `no_safe_plan` |
| API contract | all endpoints | request/response/error shapes match `BACKEND_SCHEMA.md` |
| WebSocket | connect + mutation + inbound | initial `state`; broadcast on bump; inbound ignored; events ordered by `seq` |
| Twin isolation harness | provided to Sahil | `version` unchanged after `simulate()` |
| E2E happy path | real modules, fallback planner | `POST /faults` drops availability; `POST /recovery/run` → `outcome=applied`; `GET /network/state` shows recovered availability; WS emitted `state`,`diagnosis`,`simulation`,`safety`,`recovery` |
| E2E no-safe-plan | craft an unrecoverable fault | `outcome=no_safe_plan`, `version` unchanged, UI-consumable reason present |
| E2E malformed AI | inject malformed model output | pipeline falls back or reports `diagnosis_failed`/`no_plan`; never 500 |

E2E tests live in `tests/e2e/` and are Vikash-owned. They depend on teammate
modules satisfying their §3 contracts; until then they run against fakes.
