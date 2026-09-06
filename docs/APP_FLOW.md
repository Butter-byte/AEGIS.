# AEGIS — Application Flow

**Owner:** Vikash (Integration) · **Companions:** `TRD.md`, `BACKEND_SCHEMA.md`.

Complete system flow. Teammate modules appear at **black-box** level — inputs,
outputs, position in the flow. Internal algorithms are not defined here.

Legend: `SM` = StateManager · `PL` = pipeline · `WS` = WebSocket broadcast ·
`NM` = NetworkModel (Sahil's status/path port).

---

## 1. Startup

```
uvicorn backend.main:app
  → main.py builds Ports (real modules where wired, else None)
  → AppContext.build(ports):
       seed = ports.seed_source.build_seed() -> NetworkState (version 0)   [Sahil / scaffold]
       SM initialised with seed
       Broadcaster created; SM.subscribe(publish "state" on every mutation)
       Pipeline created with the ports
  → api routes + /ws mounted
Ready.
```

Frontend: `GET /network/state` → open `/ws` → receive initial `state` frame → render.

---

## 2. Read flows (no mutation, no version change)

| Trigger | Path |
|---|---|
| Load / refresh | `GET /network/state` → `SM.get_state()` |
| Telemetry panel | `GET /telemetry` → `telemetry.derive(SM.get_state())` *(Sahil)* |
| Fault list | `GET /faults` → `faults.active()` *(Sahil)* |

If a teammate port is unwired: `501 module_not_wired`.

---

## 3. Fault injection — `POST /faults { type, target, params? }`

```
api validates FaultRequest against models/
  → faults.inject(req, SM.get_state()) -> (Fault, structural_mutations)     [Sahil]
  → batch = structural_mutations
          + set_active_faults([...])
          + NM.recompute_status(preview(state, batch))                      [Sahil]
  → SM.apply_actions(batch, reason="fault <id>")   → version += 1, re-validated, atomic
  → WS: { type:"state", payload:{ state } }   (from the SM subscriber)
       { type:"fault", payload:{ action:"injected", fault } }
  → 201 { fault, state }
```

**Invalid target / wrong type / bad params:** `faults.inject` raises →
`422 invalid_fault` or `404 invalid_target` → **no mutation, no version change,
no WS event.**

### 3.1 Clearing — `DELETE /faults/{id}`

```
unknown id → 404 not_found, no mutation
else: faults.clear(id, state) -> restore_mutations
      → same batch pattern (+ NM.recompute_status) → SM.apply_actions → version += 1
      → WS: state + { type:"fault", payload:{ action:"cleared", fault_id } }
      → 200 { state }
```

---

## 4. Recovery run — `POST /recovery/run { auto_apply: true }`

Orchestrated entirely by `PL.run()`. Every stage emits a WS event.

```
 1. snapshot = SM.get_state()            (deep copy, version V)
    WS: { type:"recovery", payload:{ run_id, stage:"started", result:null } }

 2. telemetry = telemetry.derive(snapshot)                         [Sahil]
      unwired  → outcome = "error", STOP
 3. diagnosis = diagnoser.diagnose(snapshot, telemetry, active_faults)   [Yyash]
      exception → outcome = "diagnosis_failed", STOP
    WS: { type:"diagnosis", payload:{ run_id, diagnosis } }

 4. raw = planner.plan(snapshot, diagnosis)                        [Yyash]
      each candidate → models.parse_plan(raw, snapshot)   [schema gate — Vikash]
        · closed action vocabulary + referenced-id existence + based_on_version == V
        · invalid candidate dropped
      unwired planner → outcome = "error", STOP
      zero valid      → outcome = "no_plan", STOP
    → candidates: list[RecoveryPlan]  (1..N, each ≤ 6 actions)

 5. for each plan:
      sim = twin.validate(snapshot.model_copy(deep=True), plan)    [Sahil]
        · isolated copy; live state untouched
        · exception → sim.feasible = false   (stage isolation)
      WS: { type:"simulation", payload:{ run_id, result: sim } }

      decision = safety.evaluate(snapshot, sim, plan, policy)      [Hrishi]
        · deterministic; no AI text
        · exception → reject, violation "safety_error"
      WS: { type:"safety", payload:{ run_id, decision } }

 6. approved = [ c for c if c.safety.approved and c.simulation.feasible ]

 7. approved empty → outcome = "no_safe_plan", NO mutation (version stays V), go to 10

 8. best = max(approved, key=(sim.metrics.availability, -sim.metrics.avg_latency))

 9. if auto_apply:
      executor.apply(best.plan, best.safety)                       [Vikash]
        · re-check best.plan.based_on_version == SM.current_version()
          AND best.safety.based_on_version == SM.current_version()
            mismatch → outcome = "error" (conflict), no mutation
        · batch = plan_to_mutations(best.plan, snapshot, NM)
                + NM.recompute_status(preview(snapshot, batch))
        · SM.apply_actions(batch, reason="recovery <plan.id>")  → version V+1
      WS: { type:"state", payload:{ state } }   (from the SM subscriber)
      outcome = "applied", applied_plan_id, resulting_version = V+1
    else:
      outcome = "approved_pending"

10. outcome == "error" → WS: { type:"error", payload:{ run_id, code, message } }
    WS: { type:"recovery", payload:{ run_id, stage:"completed", result } }
    → 200 RecoveryRunResult
```

### 4.1 Outcomes

| `outcome` | Meaning | Live state changed? |
|---|---|---|
| `applied` | best safe plan applied | yes (`V → V+1`) |
| `approved_pending` | a safe plan exists, `auto_apply` was false | no |
| `no_safe_plan` | candidates existed, none passed twin + safety | no |
| `no_plan` | no schema-valid candidate produced | no |
| `diagnosis_failed` | diagnosis unusable | no |
| `error` | version conflict, execution failure, or an unwired module | no |

Every outcome — `error` included — is `200` with a full `RecoveryRunResult`. Only
an unexpected exception escaping the pipeline becomes `500 internal_error`.

---

## 5. Diagnosis-only / plan-only

| Endpoint | Flow | Mutation |
|---|---|---|
| `POST /recovery/diagnose` | steps 1–3 → `Diagnosis` | none |
| `POST /recovery/plan` | steps 1–4 → `{ diagnosis, candidates }` (no simulation) | none |

---

## 6. Reset — `POST /network/reset`

```
SM.reset(ports.seed_source.build_seed())  → version += 1  (NOT reset to 0)
  → WS: { type:"state", payload:{ state } }
  → 200 NetworkState
```

---

## 7. Assigned-path service semantics (worked example)

Seed: `svc-auth` host `N2`, assigned path `N2 → N1 → N3`. A physical alternate
`N2 → N4 → N3` also exists.

```
1. cut edge N1-N3
2. faults.inject → set_edge(N1-N3, failed)
3. NM.recompute_status: svc-auth's assigned path traverses N1-N3 → status = "down"
   (the alternate N2-N4-N3 is NOT auto-selected — recompute never re-routes)
4. run recovery → planner proposes reroute(svc-auth, avoid_edges=[N1-N3])
5. twin validates: NM.resolve_path → N2-N4-N3 → feasible, availability recovers
6. safety approves
7. executor applies: set_service(svc-auth, path=[N2,N4,N3])
                   + NM.recompute_status → status = "running"
8. svc-auth is healthy again — because a recovery action reassigned its path
```

This is invariant 11. Tests: `test_e2e_pipeline.py`,
`test_models_state.py`.

---

## 8. WebSocket lifecycle

```
connect  → server sends { type:"state", seq:0, version:V, payload:{ state } }
         → server streams events as they occur
SM mutation            → { type:"state", ... }
fault injected/cleared → { type:"fault", ... }
recovery run           → recovery(started), diagnosis, simulation×N, safety×N,
                         state (if applied), recovery(completed)
run outcome = error    → { type:"error", ... }  (only for "error")
client sends a frame   → read and discarded
client sees state with version <= current → drop it
```

Ordering within a connection is guaranteed by the monotonic `seq`.

---

## 9. Error flows

| Situation | Handled | Operator sees | State |
|---|---|---|---|
| Invalid fault target/type/params | `faults` → `api` | `422`/`404` envelope | unchanged |
| Unknown fault id on delete | `api` | `404 not_found` | unchanged |
| Teammate module not wired | pipeline / route | run `outcome=error`, or `501 module_not_wired` on a direct GET | unchanged |
| Malformed / OOV plan | schema gate → pipeline | fewer/zero candidates; `no_plan` if zero | unchanged |
| Twin infeasible / twin crash | pipeline (per plan) | that candidate infeasible; others continue | unchanged |
| No candidate passes safety | pipeline | `no_safe_plan` + rejection reasons | unchanged |
| Safety crash | pipeline | that candidate rejected (`safety_error`) | unchanged |
| Version changed before execution | executor / pipeline | `outcome=error` (conflict) | unchanged |
| Unexpected bug | `api` boundary | `500 internal_error` envelope | unchanged |

**In every failure case the live `NetworkState` is unchanged unless a
safety-approved plan was successfully applied.**
