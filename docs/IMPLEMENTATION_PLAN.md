# AEGIS — Implementation Plan

**Owner:** Vikash (Integration Lead) · **Companions:** `TRD.md`, `BACKEND_SCHEMA.md`.

Phased plan. **Vikash's phases are detailed** (his responsibility). **Teammate
phases specify only what must be delivered, which contract it satisfies, and when
it integrates** — not how to build it. `tests/fakes.py` + `tests/fixtures.py` are
the integration currency: a module "integrates" when its I/O matches the fakes it
replaces and the fixtures.

---

## Status

| Phase | Owner | State |
|---|---|---|
| **P0 — structure + docs + contracts plan** | Vikash | ✅ done |
| **P1 — Vikash integration backbone** | Vikash | ✅ done (this pass) |
| P2 — network sim + telemetry | Sahil | not started |
| P3 — fault injection | Sahil | not started |
| P4 — frontend | Hrishi | not started |
| P5 — mock diagnosis + planner | Yyash | not started |
| P6 — Digital Twin | Sahil | not started |
| P7 — Safety Gate | Hrishi | not started |
| P8 — wire real modules + hardening | Vikash | not started |
| P9 — E2E + demo scenarios | all | not started |
| P10 — LLM behind the planner port | Yyash | not started |

---

## Phase 0 — Structure, docs, contracts (Vikash) ✅

- Clean local project structure; teammate placeholder packages with owner READMEs.
- Six planning documents, internally consistent (`PRD`, `TRD`, `APP_FLOW`,
  `UI_UX_BRIEF`, `BACKEND_SCHEMA`, this file). No `ARCHITECTURE.md` — folded into `TRD`.
- `BACKEND_SCHEMA.md` is the frozen source of truth for every cross-module shape.
- Project config: `pyproject.toml`, `backend/requirements.txt`, `.gitignore`.

## Phase 1 — Vikash integration backbone ✅

**Goal:** a running server + a pipeline skeleton that all three teammates can plug
real modules into without touching integration code.

| Delivered | File(s) |
|---|---|
| All canonical models + the AI-output schema gate | `backend/models/` |
| `StateManager` — single authoritative writer, versioning, subscribers, atomic reject | `backend/state/manager.py`, `mutations.py`, `preview.py` |
| Module ports (Protocols) for every teammate module | `backend/pipeline/ports.py` |
| Pipeline orchestrator — observe→diagnose→plan→schema-gate→twin→safety→execute, honest `RunOutcome`, stage isolation, WS events | `backend/pipeline/orchestrator.py` |
| Executor — refuses unapproved/mismatched/stale plans; one atomic batch; no partial apply | `backend/execution/` |
| WebSocket broadcaster (transport-agnostic) + `/ws` endpoint | `backend/events/`, `backend/api/ws.py` |
| REST routes + error envelope + composition root | `backend/api/` |
| App assembly | `backend/main.py` |
| Temporary scaffold seed (deleted once `backend/network/` lands) | `backend/state/seed.py` |
| Deterministic fakes for every port + canonical fixtures | `tests/fakes.py`, `tests/fixtures.py` |
| Integration + E2E + boundary tests | `tests/` (see `TRD.md` §11) |

**Acceptance:** `GET /network/state`, `POST /network/reset`, `/ws` work now
against the scaffold seed; the full pipeline runs end to end with fakes and
returns every `RunOutcome`; unwired modules return `module_not_wired` / `error`;
import boundaries green.

**Not in Phase 1:** any simulator, twin, diagnosis, planner, safety, or frontend
implementation. Those are other owners' phases.

---

## Phase 2 — Network simulation + telemetry (Sahil)

**Deliver:**
- `SeedSource.build_seed() -> NetworkState` — deterministic (same build ⇒ identical
  topology), connected, 15–20 nodes, all healthy, all edges active, 3–4 services **with
  assigned `path`s**, `version 0`. Passes `NetworkState` structural invariants.
- `NetworkModel.recompute_status(state) -> list[Mutation]` — status-only mutations
  that make node/edge/service `status` consistent with topology + metrics. **Must
  never re-route** a service (invariant 11).
- `NetworkModel.resolve_path(...)` — viable ordered node path or `None`, honouring
  `avoid_nodes` / `avoid_edges` / `new_host` and skipping dead nodes/edges.
- `TelemetrySource.derive(state) -> Telemetry` — pure, conforms to §3.

**Contract:** `BACKEND_SCHEMA.md` §2, §3, §14. `backend/network/` +
`backend/telemetry/` import `backend/models/` (+ `networkx`) only.

**Integrates when:** `main.py` wires `Ports(seed_source=…, network_model=…,
telemetry=…)` and the E2E tests pass against the real topology instead of the
scaffold seed. Delete `backend/state/seed.py`.

**Acceptance:** seed passes structural invariants; `network_availability` formula
agreed (D1) and documented; `recompute_status` + `resolve_path` behave for
healthy, faulted, and post-recovery states.

## Phase 3 — Fault injection (Sahil)

**Deliver:** `FaultInjector` — `inject(FaultRequest, state) -> (Fault,
list[Mutation])`, `clear(id, state) -> list[Mutation]`, `active() -> list[Fault]`.
Returns mutations; does **not** touch state. Invalid target/type/params → raise
(the route maps to `422`/`404`, no mutation).

**Contract:** `BACKEND_SCHEMA.md` §4, §13. `FaultType` is closed.

**Integrates when:** `POST /faults`, `DELETE /faults/{id}`, `GET /faults` work
against the real injector and drive visible telemetry change.

## Phase 4 — Frontend (Hrishi) — parallel from now

**Deliver:** the dark network-operations dashboard per `UI_UX_BRIEF.md`,
consuming the REST + `/ws` contracts. One REST client module, one socket module,
one server-sourced view model, no hardcoded topology, stale-frame rule.

**Contract:** `UI_UX_BRIEF.md` §3–§5. `frontend/` is created by Hrishi (Vite +
React + TS + `@xyflow/react`).

**Integrates when:** the dashboard renders the seed topology from
`GET /network/state`, updates on `/ws`, can inject a fault, and can run recovery
showing diagnosis/simulation/safety/recovery and all six `RunOutcome`s.

## Phase 5 — Mock diagnosis + planner (Yyash)

**Deliver:** deterministic `Diagnoser.diagnose(...)` and
`RecoveryPlanner.plan(...)` (`source="mock"`) producing schema-valid `Diagnosis`
and `RecoveryPlan`s (closed vocabulary, ≤ 6 actions, `based_on_version` set),
**no LLM**.

**Contract:** `BACKEND_SCHEMA.md` §5, §6. `backend/diagnosis/` +
`backend/recovery/` import `backend/models/` only — no state/execution/twin/safety.

**Acceptance:** output always passes `parse_plan`; for a killed-node fault at
least one sensible candidate; deterministic (same state → same candidates).

## Phase 6 — Digital Twin (Sahil)

**Deliver:** `DigitalTwin.validate(state_copy, plan) -> SimulationResult`.

**Contract:** `BACKEND_SCHEMA.md` §7. Operates on the passed copy; `backend/twin/`
never imports `backend/state/` or `backend/execution/`; deterministic.

**Acceptance:** `StateManager.version` unchanged after `validate()` (isolation
harness — Vikash provides); identical `(state, plan)` → identical result;
infeasible plan → `feasible=false` + reason, `metrics=null`.

## Phase 7 — Safety Gate (Hrishi)

**Deliver:** `SafetyGate.evaluate(before, simulation, plan, policy) ->
SafetyDecision`; the rule-id set it emits; `PolicyConfig` defaults.

**Contract:** `BACKEND_SCHEMA.md` §8. Deterministic; `backend/safety/` imports
`backend/models/` only; `approved` iff no `critical` violation.

**Acceptance:** per-rule golden tests; determinism (same inputs ×100 → identical);
rejects at least — availability below floor, latency degradation over limit, a
plan using a quarantined/protected node, a plan leaving a service unreachable, a
twin-infeasible plan. Thresholds resolved (D2), recorded as `policy_version`.

## Phase 8 — Wire real modules + hardening (Vikash)

- `main.py` builds `Ports` from the real modules; delete `backend/state/seed.py`.
- Twin isolation harness wired against the real twin.
- Perf check: recovery run < 5 s; reads < 100 ms.
- Fill test gaps: full pipeline outcome coverage against real modules, conflict
  handling, reconnect.

**Acceptance:** the PRD demo narrative (§8) runs without a live LLM and without
manual intervention.

## Phase 9 — E2E + three scripted demo scenarios (Sahil + all)

`backend/scenarios/` — three scenarios, each running to a known outcome:

1. **Safe reroute** — a link on a service's assigned path fails; the planner
   reroutes to an alternate; safety approves; recovered.
2. **Multi-action recovery** — a degraded node + a congested link; recovery needs
   `drain_node` + `reroute` (+ maybe `migrate_service`); twin shows staged
   improvement; safety approves.
3. **Unsafe plan rejected** — the only proposed fix targets protected
   infrastructure / partitions a service / exceeds capacity; Safety Gate returns
   `approved=false` with the failing rule named; network stays safely degraded,
   no mutation.

Exposed as `POST /scenarios/{id}/run` (contract to be added to `BACKEND_SCHEMA.md`
before implementation) and as dashboard buttons.

## Phase 10 — LLM behind the planner port (Yyash)

**Deliver:** LLM-backed `Diagnoser` / `RecoveryPlanner` behind the **same**
Protocols, structured output validated by the schema gate, one retry on malformed
output, then automatic fallback to the Phase 5 mock. `RecoveryPlan.source` reports
`"llm"` vs `"mock"`.

**Acceptance:** malformed model output → retry → fallback, never a 500, never an
invalid plan; with the LLM disabled behaviour is exactly Phase 5.

---

## Timeline (3 days, approximate)

| Day | Vikash | Sahil | Yyash | Hrishi |
|---|---|---|---|---|
| 1 AM | P0 + P1 | read contracts | read contracts | read contracts |
| 1 PM | support integration | P2 | P5 (start) | P4 (start, mock data) |
| 2 AM | isolation harness, test gaps | P3 | P5 | P4 |
| 2 PM | P8 (start) | P6 | P10 (start) | P7 |
| 3 AM | P8 → P9 | P6 finish + P9 | P10 | P7 finish + P4 wire live |
| 3 PM | P9 → demo polish | P9 | P9/polish | P9/polish |

**Critical path:** P1 → (P2 + P5) → P8 → P9. Frontend (P4) and Safety (P7) run
against the fakes/fixtures and are not on the critical path until P8.

---

## TEAM DECISIONS REQUIRED

See `BACKEND_SCHEMA.md` §15 (D1–D6). Blockers: D1 (P2), D2 (P7), D3 (P2),
D4 (P6/P7), D5 (P10), D6 (already defaulted `true`).

---

## Rules for future Claude sessions

1. **One owner per session.** If a task belongs to Sahil / Yyash / Hrishi:
   define/confirm the port, add or adjust a fake, document the requirement, stop.
2. **`BACKEND_SCHEMA.md` is authoritative.** A genuine contract change =
   PR that edits §-of-`BACKEND_SCHEMA.md` first, then the model, then dependent
   docs/tests, communicated before implementation spreads.
3. **Never weaken the invariants in `TRD.md` §3.**
4. **Git/GitHub is manual** — the team commits and pushes; Claude does not.
