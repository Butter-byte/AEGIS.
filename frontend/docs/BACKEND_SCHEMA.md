# AEGIS — Backend Schema (Canonical Shared Contracts)

**Owner:** Vikash (Canonical backend contracts)
**Status:** Draft for team ratification. Once ratified, **frozen** — additive
changes only, by PR with all four owners' sign-off.

This document defines every shape that crosses a module boundary. If a structure
is not defined here, it is **teammate-internal** and not a shared contract.

- Language of record: Python 3.11 + Pydantic v2.
- All models use `extra = "forbid"` unless stated otherwise.
- All timestamps: timezone-aware UTC `datetime`, serialized as ISO 8601
  (`2026-09-06T12:00:00Z`). Field names end in `_at`.

---

## 1. Conventions

### 1.1 Identifiers

| Entity | Pattern | Example | Assigned by |
|---|---|---|---|
| Node | `^N\d+$` | `N1` | seed / topology (Sahil) |
| Edge | `^N\d+-N\d+$`, endpoints in lexical order (`source < target`) | `N1-N2` | seed / topology (Sahil) |
| Service | `^svc-[a-z0-9-]+$` | `svc-auth` | seed / topology (Sahil) |
| Fault | `^flt-[0-9a-f]{8}$` | `flt-1a2b3c4d` | `FaultInjector` (Sahil) |
| Diagnosis | `^dx-[0-9a-f]{8}$` | `dx-9f8e7d6c` | `ai/` (Yyash) |
| RecoveryPlan | `^plan-[0-9a-f]{8}$` | `plan-4b5c6d7e` | `ai/` (Yyash) |
| Recovery run | `^run-[0-9a-f]{8}$` | `run-0011eeff` | `pipeline` (Vikash) |

Random id suffixes are 8 hex chars from `uuid4().hex[:8]`.

### 1.2 Enums

```
NodeStatus      = healthy | degraded | failed | quarantined
EdgeStatus      = active  | congested | failed
ServiceStatus   = running | degraded | down
FaultType       = kill_node | degrade_node | overload_node
                | cut_edge  | congest_edge | traffic_spike
ActionType      = reroute | drain_node | restore_node
                | migrate_service | quarantine_node | reset_link
ViolationLevel  = warning | critical
RunOutcome      = applied | approved_pending | no_safe_plan
                | no_plan | diagnosis_failed | error
WSEventType     = state | fault | diagnosis | simulation | safety | recovery | error
```

### 1.3 Versioning

- `NetworkState.version: int`, starts at `0`, strictly monotonic, `+1` per
  committed mutation.
- Never reset (including on `POST /network/reset`).
- Every WS event carries the `version` it relates to (or `null` for pipeline
  progress events not tied to a commit).
- Objects derived from a state snapshot carry `based_on_version: int`.

---

## 2. NetworkState — SHARED CONTRACT (source of truth)

Owned/created by **StateManager**. Mutated **only** by
`StateManager.apply_actions()`. Every consumer receives a deep copy.

| Field | Type | Req | Validation |
|---|---|---|---|
| `version` | `int` | yes | `>= 0`, monotonic |
| `updated_at` | `datetime` | yes | UTC |
| `nodes` | `dict[str, NodeState]` | yes | non-empty; key `== value.id` |
| `edges` | `list[EdgeState]` | yes | unique `id`; `source`/`target` ∈ `nodes` |
| `services` | `dict[str, ServiceState]` | yes | key `== value.id`; `host_node` ∈ `nodes` |
| `active_fault_ids` | `list[str]` | yes | each matches Fault id pattern; default `[]` |

**Structural invariants** (enforced by `StateManager` on every mutation):
- every `edge.source` and `edge.target` exists in `nodes`
- every `service.host_node` exists in `nodes`
- every id in `active_fault_ids` corresponds to a fault tracked by `FaultInjector`
- edge `id` equals `f"{min(source,target)}-{max(source,target)}"`

### 2.1 NodeState — SHARED CONTRACT

| Field | Type | Req | Validation | Meaning |
|---|---|---|---|---|
| `id` | `str` | yes | `^N\d+$` | node identity |
| `status` | `NodeStatus` | yes | enum | operational status |
| `cpu` | `float` | yes | `0.0–100.0` | CPU utilization % |
| `latency` | `float` | yes | `>= 0` | processing latency contribution (ms) |
| `packet_loss` | `float` | yes | `0.0–1.0` | local packet loss ratio |
| `capacity` | `float` | yes | `> 0` | max traffic units the node can route |
| `load` | `float` | yes | `>= 0` | current traffic units routed through node |

### 2.2 EdgeState — SHARED CONTRACT

| Field | Type | Req | Validation | Meaning |
|---|---|---|---|---|
| `id` | `str` | yes | `^N\d+-N\d+$`, ordered | edge identity |
| `source` | `str` | yes | node id | endpoint A (lexically smaller) |
| `target` | `str` | yes | node id | endpoint B |
| `bandwidth` | `float` | yes | `> 0` | link capacity (Mbps) |
| `latency` | `float` | yes | `>= 0` | propagation latency (ms) |
| `packet_loss` | `float` | yes | `0.0–1.0` | link packet loss ratio |
| `utilization` | `float` | yes | `0.0–1.0` | fraction of bandwidth in use |
| `status` | `EdgeStatus` | yes | enum | link status |

### 2.3 ServiceState — SHARED CONTRACT

| Field | Type | Req | Validation | Meaning |
|---|---|---|---|---|
| `id` | `str` | yes | `^svc-[a-z0-9-]+$` | service identity |
| `host_node` | `str` | yes | node id | node the service currently runs on |
| `required_bandwidth` | `float` | yes | `>= 0` | bandwidth the service needs on its path (Mbps) |
| `status` | `ServiceStatus` | yes | enum | service health |
| `depends_on` | `list[str]` | no | service ids; default `[]` | upstream services required |

> **Teammate-internal (Sahil):** how `status`, `load`, `utilization`, and
> reachability are *computed* from topology and faults. The contract only fixes
> the fields above.

---

## 3. Telemetry — SHARED CONTRACT (output of `telemetry/`, owned by Sahil)

Derived, read-only projection of `NetworkState`. Not stored in `NetworkState`.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `at` | `datetime` | yes | when derived |
| `based_on_version` | `int` | yes | source state version |
| `network_availability` | `float` | yes | `0.0–1.0`, fraction of services fully operational — **exact formula: TEAM DECISION REQUIRED** |
| `avg_latency` | `float` | yes | mean end-to-end service path latency (ms) |
| `max_latency` | `float` | yes | worst service path latency (ms) |
| `total_packet_loss` | `float` | yes | `0.0–1.0`, aggregate — semantics owned by Sahil |
| `active_nodes` | `int` | yes | nodes with status ∈ {healthy, degraded} |
| `failed_nodes` | `int` | yes | nodes with status == failed |
| `quarantined_nodes` | `int` | yes | nodes with status == quarantined |
| `congested_edges` | `int` | yes | edges with status == congested |
| `failed_edges` | `int` | yes | edges with status == failed |
| `per_node` | `dict[str, NodeTelemetry]` | yes | per-node snapshot |

`NodeTelemetry = { cpu: float, latency: float, packet_loss: float, status: NodeStatus }`

> **Teammate-internal (Sahil):** path computation, latency aggregation method,
> the availability formula (pending team decision), any smoothing/noise.

---

## 4. Diagnosis — SHARED CONTRACT (output of `ai/`, owned by Yyash)

Advisory. Consumed by the Recovery Planner and shown in the UI.

| Field | Type | Req | Validation |
|---|---|---|---|
| `id` | `str` | yes | `^dx-[0-9a-f]{8}$` |
| `created_at` | `datetime` | yes | UTC |
| `based_on_version` | `int` | yes | `>= 0` |
| `summary` | `str` | yes | 1–500 chars |
| `suspected_nodes` | `list[str]` | yes | node ids; SHOULD exist in source state; default `[]` |
| `suspected_edges` | `list[str]` | yes | edge ids; SHOULD exist in source state; default `[]` |
| `suspected_services` | `list[str]` | no | service ids; default `[]` |
| `confidence` | `float` | yes | `0.0–1.0` |
| `rationale` | `str` | yes | 1–2000 chars, natural-language explanation |

Malformed model output that cannot be coerced into this schema is **rejected by
the pipeline** (never partially accepted). `parse_diagnosis(raw)` (TRD §2.1)
validates **shape only** — it has no `NetworkState` to check suspected-id
existence against, so a diagnosis naming a non-existent node is accepted (it is
merely low quality, not a safety risk). Only `parse_plan` does referenced-id
existence checks, because plans drive execution.

> **Teammate-internal (Yyash):** prompt design, model choice, how suspicion is
> derived, confidence calibration.

---

## 5. RecoveryAction & RecoveryPlan — SHARED CONTRACT (closed vocabulary)

### 5.1 RecoveryAction

Discriminated union on `type`. `extra = "forbid"`. This vocabulary is **closed** —
the AI may emit only these. No free-form commands, code, configs, or SQL.

| `type` | Fields | Field validation |
|---|---|---|
| `reroute` | `service_id: str`, `avoid_nodes: list[str] = []`, `avoid_edges: list[str] = []` | `service_id` ∈ services; avoided ids ∈ state |
| `drain_node` | `node_id: str` | `node_id` ∈ nodes |
| `restore_node` | `node_id: str` | `node_id` ∈ nodes |
| `migrate_service` | `service_id: str`, `to_node: str` | both ∈ state; `to_node != current host` |
| `quarantine_node` | `node_id: str` | `node_id` ∈ nodes |
| `reset_link` | `edge_id: str` | `edge_id` ∈ edges |

Schema Validation (in `models/`) checks **type membership, field presence, and
referenced-id existence** against the plan's source `NetworkState`. *Feasibility*
(is there capacity? is there a path?) is decided later by the Digital Twin.

### 5.2 RecoveryPlan

| Field | Type | Req | Validation |
|---|---|---|---|
| `id` | `str` | yes | `^plan-[0-9a-f]{8}$` |
| `created_at` | `datetime` | yes | UTC |
| `based_on_version` | `int` | yes | must equal the source snapshot version |
| `targets_diagnosis` | `str` | yes | a `Diagnosis.id` |
| `strategy_label` | `str` | yes | 1–120 chars |
| `rationale` | `str` | yes | 1–2000 chars |
| `actions` | `list[RecoveryAction]` | yes | length `1–6`, order significant |
| `source` | `"llm" \| "heuristic"` | yes | provenance |

> **Teammate-internal (Yyash):** how many candidates to generate, strategy
> selection, how actions are chosen and ordered, fallback heuristic logic.
> **Teammate-internal (Sahil):** how each action type transforms state inside the
> twin.

---

## 6. SimulationResult & SafetyDecision — SHARED CONTRACTS

### 6.1 SimulationResult — output of `twin/` (owned by Sahil)

One result per candidate plan.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `plan_id` | `str` | yes | the evaluated plan |
| `based_on_version` | `int` | yes | source snapshot version |
| `feasible` | `bool` | yes | could every action be applied on the copy? |
| `infeasible_reason` | `str \| null` | yes | set iff `feasible == false` |
| `metrics` | `SimMetrics \| null` | yes | `null` iff `feasible == false` |
| `delta` | `SimDelta \| null` | yes | post-minus-pre; `null` iff infeasible |
| `errors` | `list[str]` | yes | non-fatal notes; default `[]` |
| `computed_at` | `datetime` | yes | UTC |

```
SimMetrics = {
  availability:          float   # 0.0–1.0
  avg_latency:           float   # ms
  max_latency:           float   # ms
  worst_node_load:       float   # max(load / capacity) across nodes
  unreachable_services:  list[str]
  path_count:            int     # distinct service paths resolved
}
SimDelta = { availability: float, avg_latency: float, max_latency: float }
```

> **Teammate-internal (Sahil):** simulation method, how actions mutate the copy,
> path/latency/load recomputation.

### 6.2 SafetyDecision — output of `safety/` (owned by Hrishi)

| Field | Type | Req | Meaning |
|---|---|---|---|
| `plan_id` | `str` | yes | the evaluated plan |
| `based_on_version` | `int` | yes | source snapshot version |
| `approved` | `bool` | yes | `true` iff **no `critical` violations** |
| `violations` | `list[Violation]` | yes | default `[]` |
| `evaluated` | `dict[str, float]` | yes | metric values the decision used |
| `policy_version` | `str` | yes | identifies the policy config in effect |
| `decided_at` | `datetime` | yes | UTC |

```
Violation = {
  rule:     str            # stable id, e.g. "availability_floor"
  detail:   str            # human-readable
  level:    "warning" | "critical"
}
```

> **Teammate-internal (Hrishi):** the rule implementations, ordering, message
> wording. Threshold *values*: **TEAM DECISION REQUIRED** (see §10).

---

## 7. WebSocket event schemas — SHARED CONTRACT

Envelope (every frame):

```
{
  "type":    WSEventType,
  "seq":     int,            # per-connection monotonic counter
  "at":      datetime,
  "version": int | null,     # NetworkState version this event relates to
  "payload": { ... }         # per-type, below
}
```

| `type` | When emitted | `payload` |
|---|---|---|
| `state` | on connect, and after every `StateManager` mutation | `{ "state": NetworkState }` |
| `fault` | after a fault is injected or cleared | `{ "action": "injected" \| "cleared", "fault": Fault }` |
| `diagnosis` | during a run, after diagnosis produced | `{ "run_id": str, "diagnosis": Diagnosis }` |
| `simulation` | during a run, per candidate plan simulated | `{ "run_id": str, "result": SimulationResult }` |
| `safety` | during a run, per candidate plan evaluated | `{ "run_id": str, "decision": SafetyDecision }` |
| `recovery` | run lifecycle | `{ "run_id": str, "stage": "started" \| "completed", "result": RecoveryRunResult \| null }` |
| `error` | pipeline/execution surfaced error | `{ "run_id": str \| null, "code": str, "message": str }` |

Rules: inbound frames are ignored; the WS layer never mutates state; clients drop
any `state` frame whose `version <= ` their current version.

---

## 8. REST request / response schemas — SHARED CONTRACT

| Endpoint | Request body | Success response | Codes |
|---|---|---|---|
| `GET /network/state` | — | `NetworkState` | 200 |
| `POST /network/reset` | — | `NetworkState` | 200 |
| `GET /telemetry` | — | `Telemetry` | 200 |
| `GET /faults` | — | `{ "faults": [Fault] }` | 200 |
| `POST /faults` | `FaultRequest` | `{ "fault": Fault, "state": NetworkState }` | 201 / 404 / 422 |
| `DELETE /faults/{id}` | — | `{ "state": NetworkState }` | 200 / 404 |
| `POST /recovery/diagnose` | — | `Diagnosis` | 200 / 502 |
| `POST /recovery/plan` | `PlanRequest` (optional) | `{ "diagnosis": Diagnosis, "candidates": [RecoveryPlan] }` | 200 / 502 |
| `POST /recovery/run` | `RunRequest` (optional) | `RecoveryRunResult` | 200 / 500 |

```
FaultRequest = {
  type:   FaultType,
  target: str,                 # node id or edge id per type
  params: dict[str, float] | null   # type-specific, optional
}

PlanRequest = { diagnosis_id: str | null }   # null → diagnose fresh
RunRequest  = { auto_apply: bool }           # default true

RecoveryRunResult = {
  run_id:            str,
  based_on_version:  int,
  outcome:           RunOutcome,
  message:           str,
  diagnosis:         Diagnosis | null,
  candidates: [ {
      plan:       RecoveryPlan,
      simulation: SimulationResult,
      safety:     SafetyDecision
  } ],
  applied_plan_id:   str | null,
  resulting_version: int | null,
  completed_at:      datetime
}
```

`FaultRequest.params` accepted keys (values are floats; all optional):

| `type` | keys |
|---|---|
| `kill_node` | — |
| `degrade_node` | `cpu`, `packet_loss`, `latency` |
| `overload_node` | `load` |
| `cut_edge` | — |
| `congest_edge` | `utilization`, `packet_loss` |
| `traffic_spike` | `magnitude` |

> **Teammate-internal (Sahil):** how `params` map to concrete field changes and
> how `DELETE` restores elements.

---

## 9. Error schema — SHARED CONTRACT

All non-2xx REST responses:

```
{
  "error": {
    "code":    str,             # machine-readable, from the table below
    "message": str,             # human-readable
    "details": dict | null      # optional context (field errors, ids)
  }
}
```

| `code` | HTTP | Meaning |
|---|---|---|
| `validation_error` | 422 | request body failed schema validation |
| `invalid_fault` | 422 | fault type/params invalid for target |
| `invalid_target` | 404 | referenced node/edge/service does not exist |
| `not_found` | 404 | referenced fault id / resource does not exist |
| `conflict` | 409 | state changed under the operation (version mismatch) |
| `pipeline_error` | 502 | AI stage failed irrecoverably (even fallback) |
| `execution_error` | 500 | approved plan failed to apply |
| `internal_error` | 500 | unexpected bug |
| `not_implemented` | 501 | **TEMPORARY (Phase 0/1)** — a teammate module is still stubbed. Disappears once telemetry / faults / ai / twin / safety are wired. Not a permanent part of the contract. |

Expected recovery outcomes (`no_plan`, `no_safe_plan`, `diagnosis_failed`,
`approved_pending`, **and `error`**) are **not** HTTP errors — they are
`RecoveryRunResult.outcome` values returned with HTTP 200. Only an unexpected
exception escaping the pipeline becomes `500 internal_error`.

---

## 10. TEAM DECISION REQUIRED (values, not shapes)

These fields are contractually fixed in shape here; their *values* need team
agreement before Safety/Twin/Telemetry implementation:

1. `Telemetry.network_availability` exact formula.
2. Safety policy thresholds: availability floor (suggested `>= 0.99`), max
   allowed latency degradation (suggested `+20%` vs pre-recovery), max
   `worst_node_load` (suggested `<= 0.90`), whether `warning`-level violations
   ever block.
3. Seed topology final size and the identity/count of seed `ServiceState` entries.
4. Whether `restore_node` requires the underlying fault to be cleared first
   (affects both Safety and Twin).
5. LLM provider + model, and whether the demo runs on the real LLM or the
   deterministic fallback.
6. **Edge id ordering for ≥10 nodes.** §1.1 specifies *lexical* order, so
   `edge_id_for("N2","N10") == "N10-N2"` (lexical: `"N10" < "N2"`). If the seed
   ever exceeds 9 nodes, either accept lexical ordering everywhere or switch to
   numeric ordering — a one-line change in `models/common.edge_id_for` plus the
   `EdgeState` validator, but it must be decided before Sahil builds the seed.

---

## 11. SHARED CONTRACT vs TEAMMATE INTERNAL — summary

| SHARED CONTRACT (this doc, owned by Vikash) | TEAMMATE INTERNAL (owner decides) |
|---|---|
| `NetworkState`, `NodeState`, `EdgeState`, `ServiceState` field sets | how topology/faults compute those fields (Sahil) |
| `Telemetry` field set | derivation math, availability formula (Sahil) |
| `Fault` / `FaultRequest` shape | param → field-change mapping, restore logic (Sahil) |
| `Diagnosis` shape | prompts, model, suspicion logic (Yyash) |
| `RecoveryAction` closed vocabulary, `RecoveryPlan` shape | candidate generation, action selection, fallback (Yyash) |
| `SimulationResult` / `SimMetrics` shape | simulation method, action semantics in the twin (Sahil) |
| `SafetyDecision` / `Violation` shape, approval rule (no critical) | rule implementations, threshold values (Hrishi) |
| REST + WS envelopes, error schema | — |
| id patterns, versioning, timestamp format | — |
| mutation primitives (§12) | which primitives a fault / action produces |

---

## 12. Mutation primitives — SHARED CONTRACT (`state/mutations.py`)

`StateManager.apply_actions(mutations, reason)` accepts a list of these
mechanical field-write primitives. They carry no domain semantics.

```
SetNodeFields     = { op: "set_node_fields",    node_id: str,    fields: dict[str, float|int|str|bool|list] }
SetEdgeFields     = { op: "set_edge_fields",    edge_id: str,    fields: dict[...] }
SetServiceFields  = { op: "set_service_fields", service_id: str, fields: dict[...] }
SetActiveFaults   = { op: "set_active_faults",  fault_ids: list[str] }
```

Discriminated union on `op`. Rules enforced by `StateManager`:
- unknown `node_id` / `edge_id` / `service_id` → whole batch rejected
- `fields` containing an unknown or out-of-range key → whole batch rejected
  (full `NetworkState` re-validation)
- the batch is atomic: all primitives apply or none do; `version` bumps once

**`faults/` (Sahil)** emits these from a `Fault` + params. **`execution/`
(Vikash)** emits these from an approved `RecoveryPlan`. See `ARCHITECTURE.md`
§4.3.
