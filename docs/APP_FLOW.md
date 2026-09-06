# AEGIS — Application Flow

**Owner:** Vikash (Integration)
**Companion:** `ARCHITECTURE.md`, `BACKEND_SCHEMA.md`, `TRD.md`.

Describes the complete system flow. Teammate modules are described at
**black-box** level only — inputs, outputs, and where they sit in the flow. Their
internal algorithms are not defined here.

Legend: `SM` = StateManager · `PL` = pipeline · `WS` = WebSocket broadcast.

---

## 1. Startup

```
uvicorn backend.main:app
  → main.py builds the app
  → network.build_seed() -> NetworkState (version 0)          [Sahil, black box]
  → SM initialized with that state
  → api/ routes + /ws mounted
  → WS layer subscribes to SM
Ready.
```

Frontend: `npm run dev` → loads → `GET /network/state` → opens `/ws` → receives
the initial `state` event → renders.

---

## 2. Read flows (no mutation)

| Trigger | Path | Result |
|---|---|---|
| Load dashboard / refresh | `GET /network/state` → `SM.snapshot()` | `NetworkState` |
| Telemetry panel | `GET /telemetry` → `telemetry.derive(SM.snapshot())` [Sahil, black box] | `Telemetry` |
| Fault list | `GET /faults` → `FaultInjector.active()` [Sahil, black box] | `[Fault]` |

None of these change `version`.

---

## 3. Fault injection

```
Operator clicks a fault control
  → POST /faults { type, target, params? }
  → api/ validates request shape against models/
  → FaultInjector.inject(req)                                  [Sahil, black box]
       · validates target exists and is the right kind
       · computes the resulting field mutations
  → SM.apply_actions(mutations, reason="fault <id>")
       · version += 1, updated_at set
       · structural invariants checked
       · subscribers notified
  → WS broadcast:  { type: "state",  payload: { state } }
                   { type: "fault",  payload: { action: "injected", fault } }
  → 201 { fault, state }
Frontend replaces its view model; telemetry panel re-fetches or reads next state.
```

**Invalid fault** (unknown target / wrong type / bad params):
`FaultInjector` returns a validation failure → `api/` responds `422 invalid_fault`
or `404 invalid_target` → **no mutation, no `version` change, no WS event.**

### 3.1 Clearing a fault

```
Operator clears a fault (or clicks reset-affected)
  → DELETE /faults/{id}
  → FaultInjector.clear(id)  [Sahil, black box] → restore mutations
  → SM.apply_actions(...) → version += 1
  → WS: state + { type: "fault", payload: { action: "cleared", fault } }
  → 200 { state }
```
Unknown id → `404 not_found`, no mutation.

---

## 4. Recovery run (the full cycle)

Triggered by `POST /recovery/run { auto_apply: true }`. Orchestrated entirely by
`pipeline.py`. Each stage emits a WS event.

```
PL.run():

 1. snapshot = SM.snapshot()                         # deep copy, version V
    WS: { type: "recovery", payload: { run_id, stage: "started" } }

 2. telemetry = telemetry.derive(snapshot)           [Sahil, black box]

 3. diagnosis = ai.diagnose(snapshot, faults, telemetry)     [Yyash, black box]
      · on malformed/exception: retry once → deterministic fallback
      · if still unusable → outcome = "diagnosis_failed", STOP
    WS: { type: "diagnosis", payload: { run_id, diagnosis } }

 4. raw = ai.plan(snapshot, diagnosis)               [Yyash, black box]
      · each candidate parsed by models.SchemaValidation
        (closed action vocabulary + referenced-id existence)
      · malformed / out-of-vocabulary candidates dropped
      · zero valid → deterministic fallback planner
      · still zero → outcome = "no_plan", STOP
    → candidates: list[RecoveryPlan]   (1..N, each ≤ 6 actions)

 5. for each plan in candidates:
      sim = twin.simulate(snapshot.model_copy(deep=True), plan)  [Sahil, black box]
        · isolated copy; live state untouched
        · exception → sim.feasible = False
      WS: { type: "simulation", payload: { run_id, result: sim } }

      safety = safety.evaluate(snapshot, sim, plan, policy)      [Hrishi, black box]
        · deterministic; no AI text involved
        · exception → treated as reject (violation "safety_error")
      WS: { type: "safety", payload: { run_id, decision: safety } }

 6. approved = [ c for c in candidates
                 if c.safety.approved and c.simulation.feasible ]

 7. if approved is empty:
      outcome = "no_safe_plan"
      NO mutation, version stays V
      → go to step 10

 8. best = max(approved, key=(sim.metrics.availability, -sim.metrics.avg_latency))

 9. if auto_apply:
      assert best.safety.approved and best.simulation.feasible
      execution.apply(best.plan, best.safety)        [Vikash]
        · re-check best.plan.based_on_version == SM.current_version()
          AND best.safety.based_on_version == SM.current_version()
            mismatch → outcome = "error" (reason: conflict), no mutation
        · translate actions → one mutation batch
        · SM.apply_actions(batch, reason="recovery <plan.id>")  → version V+1
      WS: { type: "state", payload: { state } }   (emitted by the SM subscriber)
      outcome = "applied", applied_plan_id = best.plan.id, resulting_version = V+1
    else:
      outcome = "approved_pending"

10. if outcome == "error":  WS: { type: "error", payload: { run_id, code, message } }
    WS: { type: "recovery", payload: { run_id, stage: "completed", result } }
    → 200 RecoveryRunResult
```

### 4.1 Outcomes

| `outcome` | Meaning | Live state changed? |
|---|---|---|
| `applied` | best safe plan was applied | yes (`V → V+1`) |
| `approved_pending` | a safe plan exists, `auto_apply` was false | no |
| `no_safe_plan` | candidates existed, none passed safety+feasibility | no |
| `no_plan` | no schema-valid candidate could be produced | no |
| `diagnosis_failed` | diagnosis unusable even after fallback | no |
| `error` | version conflict, execution failure, or an internal stage error | no |

**Every** run outcome — `error` included — is returned as `200` with a full
`RecoveryRunResult` body: the run completed and produced a description of what
happened. Only an unexpected exception that escapes the pipeline entirely is
turned into a non-2xx response (`500 internal_error`) by the `api/` boundary.

---

## 5. Diagnosis-only and plan-only flows

| Endpoint | Flow | Mutation |
|---|---|---|
| `POST /recovery/diagnose` | steps 1–3 only → returns `Diagnosis` | none |
| `POST /recovery/plan` | steps 1–4 only → returns `{ diagnosis, candidates }` (no simulation) | none |

These let the frontend show diagnosis/candidates before committing to a full run.

---

## 6. Reset

```
Operator clicks "Reset"
  → POST /network/reset
  → SM.reset(): network.build_seed() → mutation batch
  → SM.apply_actions(...) → version += 1   (version is NOT reset to 0)
  → FaultInjector active set cleared
  → WS: { type: "state", payload: { state } }
  → 200 NetworkState
```

---

## 7. WebSocket lifecycle

```
Client connects to /ws
  → server sends { type: "state", seq: 0, version: V, payload: { state } }
  → server streams events as they occur

Every SM mutation           → { type: "state", ... }
Fault injected / cleared     → { type: "fault", ... }
During a recovery run       → recovery(started), diagnosis, simulation (×N),
                              safety (×N), recovery(completed)
Recovery run outcome=error  → { type: "error", payload: { run_id, code, message } }
                              (only for outcome=error — no_plan / no_safe_plan /
                              diagnosis_failed are normal outcomes, not errors)

Client sends a frame        → read and discarded (never mutates, never runs)
Connection drops            → client reconnects, gets a fresh initial state frame
Client receives state with version <= its current → drop it
```

Event ordering within a connection is guaranteed by the monotonic `seq` counter.

---

## 8. Error flows (summary)

| Situation | Where handled | Operator sees | State |
|---|---|---|---|
| Invalid fault target/type/params | `FaultInjector` → `api/` | `422`/`404` error body | unchanged |
| Unknown fault id on delete | `FaultInjector` → `api/` | `404 not_found` | unchanged |
| Malformed AI diagnosis | `ai/` retry + fallback; else `PL` | diagnosis (fallback) or `outcome=diagnosis_failed` | unchanged |
| Malformed / out-of-vocabulary plan | `models.SchemaValidation` → `PL` | fewer/zero candidates; `outcome=no_plan` if zero | unchanged |
| Impossible recovery action | `twin` → `sim.feasible=False` | that candidate marked infeasible | unchanged |
| Digital twin crash mid-run | `PL` catches per plan | that candidate infeasible; others continue | unchanged |
| No candidate passes safety | `PL` | `outcome=no_safe_plan` + rejection reasons | unchanged |
| Safety engine crash | `PL` catches → reject | that candidate rejected (`safety_error`) | unchanged |
| Version changed before execution | `execution` / `PL` | `outcome=error`, `code=conflict` | unchanged |
| Execution translation failure | `execution` | `500 execution_error` | unchanged |
| Unexpected bug | `api/` boundary | `500 internal_error` (error schema) | unchanged |

**In every failure case, the live `NetworkState` is left unchanged unless a
safety-approved plan was successfully applied.**
