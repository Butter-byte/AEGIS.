# AEGIS — Implementation Plan

**Owner:** Vikash (Integration Lead)
**Companion:** `ARCHITECTURE.md`, `BACKEND_SCHEMA.md`, `TRD.md`.

Phased plan for the 3-day MVP. **Vikash's phases are detailed** (his
responsibility). **Teammate phases specify only what must be delivered, which
contract it must satisfy, and when it integrates** — not how to build it.

Contract fixtures in `tests/contracts/` are the integration currency: a module
"integrates" when its I/O matches the fixtures.

---

## Phase 0 — Foundation & contract freeze  ·  Owner: Vikash  ·  ~half day

**Goal:** every teammate can start in parallel against a stable contract.

| Task | Detail |
|---|---|
| Ratify `BACKEND_SCHEMA.md` | team read-through; resolve or park the §10 TEAM DECISION items |
| `backend/models/` | implement all 11 canonical models + `RecoveryAction` union + request/response + WS envelope + error model + enums + `SchemaValidation` helpers |
| `backend/state/StateManager` | `snapshot()`, `apply_actions()`, `reset()`, `subscribe()`, `current_version()`; structural-invariant checks; version monotonicity |
| `backend/config.py` | seed params, safety thresholds (placeholder), LLM settings |
| `tests/contracts/` | one valid + several invalid instances of every model |
| Repo hygiene | `.gitignore`; `backend/requirements.txt` (pinned); remove committed `__pycache__`; pin Python 3.11 (**INFORM Sahil** — his commits added the bytecode) |
| Fake modules | `fakes/` providing stub `ai`, `twin`, `safety`, `telemetry`, `build_seed` matching the fixtures, so the pipeline and API can be built before real modules land |

**Dependency:** none.
**Integration point:** publishes `models/` + fixtures + `StateManager`.
**Acceptance:**
- every model round-trips through its fixture; invalid variants raise
- `StateManager` unit tests pass (S1–S9 in `TRD.md §2.2`)
- import-lint test in place and green

---

## Phase 1 — StateManager + API skeleton + WebSocket  ·  Owner: Vikash  ·  ~half day

**Goal:** a running server that serves state and broadcasts changes, using fakes.

| Task | Detail |
|---|---|
| `backend/api/` routes | all endpoints from `TRD.md §5`, delegating to fakes where real modules are absent |
| Error mapping | exceptions → error schema (`BACKEND_SCHEMA.md §9`) |
| `backend/api/ws.py` | `/ws` broadcast; initial `state` frame; `StateManager` subscription; `publish(event)` sink; inbound ignored |
| `backend/main.py` | app assembly; seed load at startup |
| Tests | API contract tests; WS connect/broadcast/inbound-ignored test |

**Dependency:** Phase 0.
**Integration point:** live REST + WS surface for the frontend and for e2e tests.
**Acceptance:**
- `GET /network/state`, `GET /telemetry`, `GET /faults` return valid shapes
- `POST /faults` (via fake injector) bumps `version` and broadcasts `state`+`fault`
- `/ws` sends initial state and rebroadcasts on mutation; inbound frames ignored

---

## Phase 2 — Network simulation, topology, telemetry  ·  Owner: Sahil

**Must deliver:**
- `network.build_seed() -> NetworkState` — valid per `BACKEND_SCHEMA.md §2`
  (connected, ≥5 nodes healthy, all edges active, ≥3 services, `version 0`).
- `telemetry.derive(state) -> Telemetry` — pure, conforms to §3.
- `NetworkState ↔ graph` helpers for downstream algorithm use.

**Contract to satisfy:** `BACKEND_SCHEMA.md §2, §3`; telemetry is a pure function
with no side effects; nothing writes `NetworkState` directly.

**Integrates when:** `build_seed()` output parses against the fixtures and
`StateManager` accepts it; `GET /telemetry` returns real data.

**Acceptance (contract-level):**
- seed passes `StateManager` structural invariants
- telemetry fields all present and in range for the seed and for a faulted state
- `network_availability` formula agreed (TEAM DECISION) and documented by Sahil

**Not specified here:** topology shape, path/latency/load model, availability math.

---

## Phase 3 — Fault injection  ·  Owner: Sahil

**Must deliver:** `FaultInjector` with
`inject(FaultRequest) -> (Fault, mutations)`, `clear(id) -> mutations`,
`active() -> list[Fault]`; applied **only** via `StateManager.apply_actions()`.

**Contract to satisfy:** `Fault` / `FaultRequest` shapes (`§8`); invalid
target/type/params rejected with no mutation; `FaultType` vocabulary is closed.

**Integrates when:** `POST /faults`, `DELETE /faults/{id}`, `GET /faults` work
against the real injector and drive visible telemetry change.

**Acceptance (contract-level):**
- each `FaultType` produces a visible, consistent state change
- invalid requests → `422`/`404`, `version` unchanged
- `clear` moves affected elements toward nominal

**Not specified here:** how each fault maps to concrete field changes.

---

## Phase 4 — Frontend observability  ·  Owner: Hrishi  ·  starts in parallel from Phase 1

**Must deliver:** dashboard rendering **live** `NetworkState` + `Telemetry` +
fault list; fault controls; a recovery panel; consumption of `/ws` events;
`services/api.ts` + `services/socket.ts`.

**Contract to satisfy:** `UI_UX_BRIEF.md §3–§5`; single server-sourced view
model; no hardcoded topology; stale-frame rule.

**Integrates when:** the dashboard shows the seed topology from `GET
/network/state`, updates on `/ws` `state` events, and can inject a fault.

**Acceptance (contract-level):**
- topology and telemetry reflect server state, update in real time
- fault inject/clear works end to end
- recovery panel renders `diagnosis` / `simulation` / `safety` / `recovery`
  events and all six `RunOutcome` values
- reconnect falls back to `GET /network/state`

**Not specified here:** visual design, components, layout, styling, motion.

---

## Phase 5 — Mock diagnosis + mock recovery planner  ·  Owner: Yyash

**Must deliver:** deterministic `ai.diagnose(...)` and `ai.plan(...)` with
`source="heuristic"`, producing schema-valid `Diagnosis` and `RecoveryPlan`s
(closed vocabulary, ≤6 actions, `based_on_version` set) with **no LLM**.

**Contract to satisfy:** `BACKEND_SCHEMA.md §4, §5`; `ai/` imports `models/`
only; returns data; never touches state/execution/twin/safety.

**Integrates when:** `POST /recovery/diagnose` and `POST /recovery/plan` return
real (heuristic) data and the pipeline can consume it.

**Acceptance (contract-level):**
- output always parses via `models.SchemaValidation`
- for a killed-node fault, at least one sensible candidate is produced
- deterministic: same state → same candidates

**Not specified here:** heuristic logic, strategy selection.

---

## Phase 6 — Digital Twin  ·  Owner: Sahil

**Must deliver:** `twin.simulate(state_copy, plan) -> SimulationResult`.

**Contract to satisfy:** `BACKEND_SCHEMA.md §6.1`; operates on the passed copy;
`twin/` never imports `state/` or `execution/`; deterministic.

**Integrates when:** the pipeline can simulate each candidate and get comparable
metrics.

**Acceptance (contract-level):**
- `StateManager.version` unchanged after `simulate()` (Vikash's isolation harness)
- identical `(state, plan)` → identical `SimulationResult`
- infeasible plan → `feasible=False` + `infeasible_reason`, `metrics=null`
- feasible plan → all `SimMetrics` present; `delta` computed

**Not specified here:** simulation method, per-action state transforms, metric math.

---

## Phase 7 — Safety Engine  ·  Owner: Hrishi

**Must deliver:** `safety.evaluate(before, sim, plan, policy) -> SafetyDecision`;
a `PolicyConfig` with default thresholds; the set of rule ids it emits.

**Contract to satisfy:** `BACKEND_SCHEMA.md §6.2`; deterministic; `safety/`
imports `models/` only; `approved` iff no `critical` violation.

**Integrates when:** the pipeline gets a real decision per candidate.

**Acceptance (contract-level):**
- per-rule golden tests (crafted metrics → expected violation)
- determinism: same inputs ×100 → identical `SafetyDecision`
- rejects: availability below floor; latency degradation over limit; plan uses a
  quarantined node; plan leaves a service unreachable; twin-infeasible plan
- thresholds resolved (TEAM DECISION) and recorded as `policy_version`

**Not specified here:** rule implementations, evaluation order, messages.

---

## Phase 8 — Execution + full pipeline wiring  ·  Owner: Vikash  ·  ~half day

**Goal:** the real end-to-end cycle with all real modules.

| Task | Detail |
|---|---|
| `backend/execution/` | `apply(plan) -> ExecutionResult` per `TRD.md §2.4` (E1–E6); version re-check; single atomic mutation batch; no partial apply |
| `pipeline.run()` | replace fakes with real `ai` / `twin` / `safety` / `telemetry`; implement stage isolation, fallback rules, outcome mapping (`ARCHITECTURE.md §5`) |
| WS progress events | emit `diagnosis` / `simulation` / `safety` / `recovery` at stage boundaries |
| Tests | pipeline integration across every `RunOutcome`; execution unit tests; conflict handling |

**Dependency:** Phases 2, 3, 5, 6, 7 at contract level (fakes stand in for any
that slip).
**Integration point:** `POST /recovery/run` performs the real cycle.
**Acceptance:**
- happy path: fault → run → `outcome=applied`, `version` bumped once, WS events
  in order
- `no_safe_plan`: crafted unrecoverable fault → no mutation, reasons present
- execution never runs without `approved && feasible` for the current `version`
- version conflict → `outcome=error`, no mutation

---

## Phase 9 — End-to-end integration & hardening  ·  Owner: Vikash  ·  ~half day

| Task | Detail |
|---|---|
| `tests/e2e/` | happy path, no-safe-plan, malformed-AI, reset, reconnect |
| Import-lint | full forbidden-dependency table green (`ARCHITECTURE.md §8.1`) |
| Twin isolation test | wired against the real twin |
| Frontend ↔ backend | full manual pass of `UI_UX_BRIEF.md §4` states |
| Perf check | recovery run < 5 s (fallback); reads < 100 ms |

**Acceptance:** the PRD demo narrative (`PRD.md §8`) runs without a live LLM and
without manual intervention.

---

## Phase 10 — Structured LLM integration  ·  Owner: Yyash

**Must deliver:** real LLM-backed `ai.diagnose` / `ai.plan` behind the **same**
function signatures, with structured output validated by `models.SchemaValidation`,
one retry on malformed output, then automatic fallback to the Phase 5 heuristic.

**Contract to satisfy:** identical to Phase 5 — output types unchanged; `ai/`
still imports `models/` only; malformed output never propagates.

**Integrates when:** setting the LLM key switches diagnosis/planning to the model
with no change to the pipeline or API.

**Acceptance (contract-level):**
- malformed model output → retry → fallback, never a 500, never an invalid plan
- with the LLM disabled, behaviour is exactly Phase 5
- `RecoveryPlan.source` correctly reports `llm` vs `heuristic`

**Not specified here:** prompts, model, provider, structured-output mechanism.

---

## Phase 11 — Testing pass  ·  Owner: all, coordinated by Vikash

Fill gaps against `ARCHITECTURE.md §9`. Priorities: safety golden tests,
malformed-AI tests, twin isolation/determinism, pipeline outcome coverage,
import-lint.

---

## Phase 12 — Demo polish  ·  Owner: all

Scripted fault→recovery scenario; ensure `no_safe_plan` path is demoable;
event-log readability; a second unrecoverable fault for the contrast moment.

---

## Timeline (3 days, approximate)

| Day | Vikash | Sahil | Yyash | Hrishi |
|---|---|---|---|---|
| 1 AM | Phase 0 | (read contract) | (read contract) | (read contract) |
| 1 PM | Phase 1 | Phase 2 | Phase 5 (start) | Phase 4 (start, mock mode) |
| 2 AM | (support) | Phase 3 | Phase 5 | Phase 4 |
| 2 PM | Phase 8 (start) | Phase 6 | Phase 10 (start) | Phase 7 |
| 3 AM | Phase 8 → 9 | Phase 6 finish | Phase 10 | Phase 7 finish + Phase 4 wire live |
| 3 PM | Phase 9 → 12 | Phase 11/12 | Phase 11/12 | Phase 11/12 |

**Critical path:** Phase 0 → (Phase 2 + Phase 5) → Phase 8 → Phase 9.
Phase 4 (frontend) and Phase 7 (safety) run against fixtures/fakes and are not on
the critical path until Phase 9.

---

## Why this order (deviations from the suggested sequence)

- **Contract freeze is an explicit gate (Phase 0), not folded into "foundation."**
  Parallel work is impossible until the schemas exist. Highest-leverage step.
- **Twin (6) and Safety (7) proceed in parallel.** Safety only needs the
  `SimulationResult` *shape* — Hrishi builds against hand-written fixtures, so
  he is not blocked on Sahil.
- **Mock diagnosis/planner (5) before real LLM (10).** The whole safety-gated
  pipeline must be demoable with zero LLM dependency. The LLM is a drop-in at
  Phase 10; if it slips, the demo still works.
- **Frontend (4) is continuous from Phase 1, not a discrete later phase.** Hrishi
  needs the full three days; he is gated only on the frozen API/WS shapes plus a
  mock mode in `services/`.
- **Telemetry is part of Phase 2, not its own subsystem.** It is a pure
  projection of `NetworkState`; treating it as an "engine" is over-scoped.

---

## TEAM DECISION REQUIRED (blockers for the phases that need them)

| # | Decision | Needed by | Suggested default |
|---|---|---|---|
| D1 | `Telemetry.network_availability` formula | Phase 2 | fraction of services with `status == running` |
| D2 | Safety thresholds: availability floor / max latency degradation / max node load / do warnings block | Phase 7 | `>= 0.99` / `+20%` / `<= 0.90` / warnings do not block |
| D3 | Seed topology final size + seed service count/identity | Phase 2 | ~7–12 nodes, 3–4 services |
| D4 | Does `restore_node` require the underlying fault cleared first | Phases 6, 7 | yes |
| D5 | LLM provider + model; is the real LLM in demo scope | Phase 10 | fallback is the demo; LLM is a bonus |
| D6 | `auto_apply` default for `POST /recovery/run` | Phase 8 | `true` |

---

## INFORM [TEAMMATE] — issues found in teammate-owned areas (not fixed here)

### INFORM Sahil

**Issue:** `backend/network/simulator.py` makes its `networkx.Graph` the de facto
source of truth, and `backend/api/routes.py` holds a module-level
`sim = NetworkSimulator()` singleton. Faults mutate the graph directly.
**Why it matters:** violates architectural invariants 1 and 2 —
`NetworkState` must be the single source of truth and `StateManager` its only
writer. The current design has no `StateManager`, no `version`, and no path for
execution/telemetry to share one state.
**What needs to be discussed:** reframing the simulator as (a) a `build_seed() ->
NetworkState` producer and (b) stateless graph/algorithm helpers that operate on
a `NetworkState` passed in; all mutations routed through
`StateManager.apply_actions()`. The `nx.Graph` can remain an internal
computation detail, rebuilt from `NetworkState` as needed.

**Issue:** the seed topology is hardcoded to 7 nodes (`N1`–`N7`) in
`_build_initial_topology`, with no services, no `capacity`/`load`, and edges
without `id`/`utilization`.
**Why it matters:** the canonical `NetworkState` (`BACKEND_SCHEMA.md §2`)
requires those fields and a `services` map; `migrate_service` and the
availability metric depend on services existing.
**What needs to be discussed:** the seed's final node count, the service set (D3),
and populating the additional fields.

**Issue:** `origin/frontend` renders its own hardcoded 5-node topology (`N1`–`N5`)
that does not match the backend's 7 nodes.
**Why it matters:** two diverging topologies = two sources of truth (invariant
11).
**What needs to be discussed:** frontend must render `NetworkState` from the API;
the seed (yours) is the only topology. (Also raised with Hrishi.)

**Issue:** committed bytecode — `backend/**/__pycache__/*.cpython-311.pyc` — is
in the repo, and there is no `.gitignore` or `requirements.txt`. Bytecode is
CPython 3.11 while the local interpreter is 3.14.
**Why it matters:** dirty diffs, wrong-interpreter confusion, no reproducible
env.
**What needs to be discussed:** Vikash will add `.gitignore` + pinned
`requirements.txt` + pin Python 3.11 in Phase 0 and remove the tracked `.pyc`
files; flagging so the removal in your working tree is expected.

### INFORM Yyash

**Issue:** no `ai/` module exists yet; there is no structured-output or fallback
mechanism.
**Why it matters:** the pipeline requires `ai.diagnose` / `ai.plan` to return
schema-valid `Diagnosis` / `RecoveryPlan` data and to never propagate malformed
output. Without a deterministic fallback, the entire demo depends on a live LLM
(NFR2 forbids that).
**What needs to be discussed:** committing to the closed `RecoveryAction`
vocabulary (`BACKEND_SCHEMA.md §5`), and delivering the Phase 5 heuristic
diagnosis/planner before the Phase 10 LLM integration.

### INFORM Hrishi

**Issue:** no `safety/` module exists yet.
**Why it matters:** it is the authority in the pipeline; it must be deterministic
and independent of the AI (invariants 8, 9).
**What needs to be discussed:** the `evaluate()` signature (`TRD.md §3.4`), the
`PolicyConfig` thresholds (D2), and the rule id set it will emit.

**Issue:** the `origin/frontend` dashboard is fully hardcoded — mocked telemetry
("CPU 42%", "12 active nodes"), a hardcoded 5-node graph, non-functional fault
buttons — and has no `services/` API or socket layer.
**Why it matters:** invariant 11 (no second state store); the frontend must
render live `NetworkState`.
**What needs to be discussed:** replacing hardcoded data with `services/api.ts` +
`services/socket.ts` consuming the real endpoints; the graph deriving nodes/edges
from `NetworkState`.

**Issue:** `frontend/package.json` on `origin/frontend` pins versions that do not
resolve (`react ^19.2.8`, `vite ^8.2.2`, `typescript ~6.0.2`, `eslint ^10`, etc.).
**Why it matters:** `npm install` will fail; the frontend can't be built or run.
**What needs to be discussed:** a real install/pin pass early in Phase 4.
