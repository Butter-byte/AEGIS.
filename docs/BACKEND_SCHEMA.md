# AEGIS — Backend Schema (Canonical Shared Contracts)

**Owner:** Vikash. **Status:** draft for ratification, then **frozen** — additive
changes only, by PR with all four owners' sign-off.

Every shape that crosses a module boundary is defined here. If a structure is not
here, it is **teammate-internal** and not a shared contract. Implemented in
`backend/models/` (a leaf package). Language of record: Python 3.11+ / Pydantic v2.
All models set `extra = "forbid"`. Timestamps are timezone-aware UTC, serialised
as ISO-8601 with `Z` (`2026-09-06T12:00:00Z`); field names end in `_at`.

---

## 1. Conventions

### 1.1 Identifiers

| Entity | Pattern | Example | Assigned by |
|---|---|---|---|
| Node | `^N\d+$` | `N1` | seed / topology (Sahil) |
| Edge | `^N\d+-N\d+$`, endpoints ordered by **node number** | `N2-N10` | seed / topology (Sahil) |
| Service | `^svc-[a-z0-9-]+$` | `svc-auth` | seed / topology (Sahil) |
| Fault | `^flt-[0-9a-f]{8}$` | `flt-1a2b3c4d` | FaultInjector (Sahil) |
| Diagnosis | `^dx-[0-9a-f]{8}$` | `dx-9f8e7d6c` | Diagnoser (Yyash) |
| RecoveryPlan | `^plan-[0-9a-f]{8}$` | `plan-4b5c6d7e` | RecoveryPlanner (Yyash) |
| SimulationResult | `^sim-[0-9a-f]{8}$` | `sim-1122aabb` | Digital Twin (Sahil) |
| Recovery run | `^run-[0-9a-f]{8}$` | `run-0011eeff` | pipeline (Vikash) |

Random suffixes: `uuid4().hex[:8]`. **Edge ids order endpoints numerically**, so
`edge_id_for("N2","N10") == "N2-N10"` — stable past 9 nodes.
(`backend/models/common.edge_id_for`.)

### 1.2 Enums (closed)

```
NodeStatus     = healthy | degraded | failed | quarantined
EdgeStatus     = active  | congested | failed
ServiceStatus  = running | degraded | down
FaultType      = kill_node | degrade_node | overload_node
               | cut_edge  | congest_edge | traffic_spike
ActionType     = reroute | drain_node | restore_node
               | migrate_service | quarantine_node | reset_link
ViolationLevel = warning | critical
RunOutcome     = applied | approved_pending | no_safe_plan
               | no_plan | diagnosis_failed | error
WSEventType    = state | fault | diagnosis | simulation | safety | recovery | error
```

### 1.3 Versioning

- `NetworkState.version: int`, starts at `0`, strictly monotonic, `+1` per
  committed mutation, **never reset** (including `POST /network/reset`).
- Every object derived from a snapshot carries `based_on_version: int`.
- Every WS event carries the `version` it relates to, or `null` for progress
  events not tied to a commit.

---

## 2. NetworkState — the source of truth

Owned by `StateManager`. Mutated only via `StateManager.apply_actions()`. Every
consumer gets a deep copy.

| Field | Type | Req | Validation |
|---|---|---|---|
| `version` | int | yes | `>= 0`, monotonic |
| `updated_at` | datetime | yes | UTC, aware |
| `nodes` | `dict[str, NodeState]` | yes | non-empty; key `== value.id` |
| `edges` | `list[EdgeState]` | yes | unique `id`; endpoints ∈ `nodes` |
| `services` | `dict[str, ServiceState]` | yes | key `== value.id`; see §2.3 |
| `active_fault_ids` | `list[str]` | yes | each matches Fault id pattern; default `[]` |

Structural invariants (enforced on every mutation): every edge endpoint ∈ nodes;
edge `id == edge_id_for(source,target)` with `source`/`target` in numeric order;
no duplicate edge id; every `service.host_node` ∈ nodes; every `service.depends_on`
∈ services; the `ServiceState.path` rules in §2.3.

### 2.1 NodeState

| Field | Type | Req | Validation | Meaning |
|---|---|---|---|---|
| `id` | str | yes | `^N\d+$` | identity |
| `status` | NodeStatus | yes | enum | operational status |
| `cpu_percent` | float | yes | `0–100` | CPU utilisation, percentage points |
| `latency_ms` | float | yes | `>= 0` | processing latency contribution (ms) |
| `packet_loss_percent` | float | yes | `0–100` | local packet loss, percentage points |
| `capacity` | float | yes | `> 0` | max traffic units the node can route |
| `load` | float | yes | `>= 0` | current traffic units routed through the node |

### 2.2 EdgeState

| Field | Type | Req | Validation | Meaning |
|---|---|---|---|---|
| `id` | str | yes | `^N\d+-N\d+$`, numeric order | identity |
| `source` | str | yes | node id (lower number) | endpoint A |
| `target` | str | yes | node id (higher number) | endpoint B |
| `bandwidth_mbps` | float | yes | `> 0` | link capacity (Mbps) |
| `latency_ms` | float | yes | `>= 0` | propagation latency (ms) |
| `packet_loss_percent` | float | yes | `0–100` | link packet loss, percentage points |
| `utilization_percent` | float | yes | `0–100` | bandwidth in use, percentage points |
| `status` | EdgeStatus | yes | enum | link status |

### 2.3 ServiceState

| Field | Type | Req | Default | Validation / meaning |
|---|---|---|---|---|
| `id` | str | yes | — | `^svc-[a-z0-9-]+$` |
| `host_node` | str | yes | — | node the service runs on |
| `required_bandwidth` | float | yes | — | `>= 0`, Mbps needed on the path |
| `status` | ServiceStatus | yes | — | service health — **see rule below** |
| `depends_on` | `list[str]` | no | `[]` | upstream service ids |
| `path` | `list[str]` | no | `[]` | the **assigned** ordered node route |

**`path` rules (structural, enforced by `NetworkState`):** when non-empty,
`path[0] == host_node`; every hop ∈ nodes; every consecutive pair has an edge
(any status).

**Status rule (contract — invariant 11):** `status` is evaluated **against the
assigned `path`**, not against whether some alternate path exists.

- `path` is reassigned **only** by an executed `reroute` or `migrate_service`
  action. Status recomputation (`NetworkModel.recompute_status`) never changes
  `path`.
- Therefore a fault on the assigned path degrades/downs the service and it stays
  that way until a safety-approved recovery reroutes it — even while a physical
  alternate exists the whole time.

*Teammate-internal (Sahil):* the exact `status` derivation (thresholds, degraded
vs down, dependency propagation, load/latency math). The contract fixes only:
status follows the assigned path; recompute never re-routes.

---

## 3. Telemetry — output of `backend/telemetry/` (Sahil)

Derived, read-only projection of `NetworkState`. Never stored in it.

| Field | Type | Meaning |
|---|---|---|
| `at` | datetime | when derived |
| `based_on_version` | int | source state version |
| `network_availability` | float `0–1` | fraction of services operational — **formula: TEAM DECISION D1** |
| `avg_latency` | float | mean end-to-end service path latency (ms) |
| `max_latency` | float | worst service path latency (ms) |
| `total_packet_loss` | float `0–1` | aggregate — semantics owned by Sahil |
| `active_nodes` | int | status ∈ {healthy, degraded} |
| `failed_nodes` | int | status == failed |
| `quarantined_nodes` | int | status == quarantined |
| `congested_edges` | int | status == congested |
| `failed_edges` | int | status == failed |
| `per_node` | `dict[str, NodeTelemetry]` | per-node snapshot |

`NodeTelemetry = { cpu_percent, latency_ms, packet_loss_percent, status }` — a
1:1 projection of the `NodeState` metrics (same names, same units).

---

## 4. Fault / FaultRequest — `backend/faults/` (Sahil), route by Vikash

```
FaultRequest = { type: FaultType, target: str (node id | edge id), params: dict[str,float] | null }
Fault        = { id, type, target, params: dict[str,float], created_at }
```

`params` accepted keys (floats, all optional; names mirror the `NodeState` /
`EdgeState` field they drive):

| `type` | keys | `target` |
|---|---|---|
| `kill_node` | — | node id |
| `degrade_node` | `cpu_percent`, `packet_loss_percent`, `latency_ms` | node id |
| `overload_node` | `load` | node id |
| `cut_edge` | — | edge id |
| `congest_edge` | `utilization_percent`, `packet_loss_percent` | edge id |
| `traffic_spike` | `magnitude` | node id or edge id |

*Teammate-internal (Sahil):* how `params` map to field changes; how `clear`
restores elements.

---

## 5. Diagnosis — output of `backend/diagnosis/` (Yyash)

Advisory. Consumed by the planner and shown in the UI.

| Field | Type | Req | Validation |
|---|---|---|---|
| `id` | str | yes | `^dx-[0-9a-f]{8}$` |
| `created_at` | datetime | yes | UTC |
| `based_on_version` | int | yes | `>= 0` |
| `summary` | str | yes | 1–500 chars |
| `suspected_nodes` | `list[str]` | yes | node ids; default `[]` |
| `suspected_edges` | `list[str]` | yes | edge ids; default `[]` |
| `suspected_services` | `list[str]` | no | service ids; default `[]` |
| `confidence` | float | yes | `0–1` |
| `rationale` | str | yes | 1–2000 chars |
| `source` | str | no | `"mock" | "heuristic" | "llm"`; default `"mock"` |

`parse_diagnosis(raw)` (the schema gate) validates **shape only** — a diagnosis
naming a non-existent node is accepted (low quality, not a safety risk). Only
`parse_plan` does referenced-id existence checks, because plans drive execution.

---

## 6. RecoveryAction & RecoveryPlan — the closed vocabulary (Yyash)

### 6.1 RecoveryAction — discriminated union on `type`, `extra = "forbid"`

| `type` | Fields | `parse_plan` id checks |
|---|---|---|
| `reroute` | `service_id`, `avoid_nodes: list[str]=[]`, `avoid_edges: list[str]=[]` | `service_id` ∈ services; avoided ids ∈ state |
| `drain_node` | `node_id` | ∈ nodes |
| `restore_node` | `node_id` | ∈ nodes |
| `migrate_service` | `service_id`, `to_node` | both ∈ state |
| `quarantine_node` | `node_id` | ∈ nodes |
| `reset_link` | `edge_id` | ∈ edges |

This vocabulary is **closed**. A planner may emit only these. Feasibility (is
there a path? is there capacity?) is decided later by the Digital Twin.

### 6.2 RecoveryPlan

| Field | Type | Req | Validation |
|---|---|---|---|
| `id` | str | yes | `^plan-[0-9a-f]{8}$` |
| `created_at` | datetime | yes | UTC |
| `based_on_version` | int | yes | must equal the source snapshot version |
| `targets_diagnosis` | str | yes | a `Diagnosis.id` |
| `strategy_label` | str | yes | 1–120 chars |
| `rationale` | str | yes | 1–2000 chars |
| `actions` | `list[RecoveryAction]` | yes | length `1–6`, order significant |
| `source` | str | yes | `"mock" | "heuristic" | "llm"` |

---

## 7. SimulationResult — output of `backend/twin/` (Sahil)

One per candidate plan.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `id` | str | yes | `^sim-[0-9a-f]{8}$` |
| `plan_id` | str | yes | the evaluated plan |
| `based_on_version` | int | yes | source snapshot version |
| `feasible` | bool | yes | could every action be applied on the copy? |
| `infeasible_reason` | str \| null | yes | set iff `feasible == false` |
| `metrics` | `SimMetrics` \| null | yes | `null` iff `feasible == false` |
| `delta` | `SimDelta` \| null | yes | post − pre; `null` iff infeasible |
| `errors` | `list[str]` | yes | non-fatal notes; default `[]` |
| `computed_at` | datetime | yes | UTC |

```
SimMetrics = { availability: float 0-1, avg_latency: float, max_latency: float,
               worst_node_load: float,  # max(load/capacity)
               unreachable_services: list[str], path_count: int }
SimDelta   = { availability: float, avg_latency: float, max_latency: float }
```

---

## 8. SafetyDecision — output of `backend/safety/` (Hrishi)

| Field | Type | Req | Meaning |
|---|---|---|---|
| `plan_id` | str | yes | the evaluated plan |
| `based_on_version` | int | yes | source snapshot version |
| `approved` | bool | yes | `true` iff **no `critical` violations** |
| `violations` | `list[Violation]` | yes | default `[]` |
| `evaluated` | `dict[str, float]` | yes | metric values the decision used |
| `policy_version` | str | yes | identifies the policy config in effect |
| `decided_at` | datetime | yes | UTC |

```
Violation = { rule: str, detail: str, level: "warning" | "critical" }
PolicyConfig = { policy_version: str = "p0-scaffold",
                 availability_floor: float = 0.99,
                 max_latency_increase_ratio: float = 0.20,
                 max_node_load_ratio: float = 0.90,
                 warnings_block: bool = false }
```

*Teammate-internal (Hrishi):* rule implementations, ordering, wording; threshold
**values** (TEAM DECISION D2).

---

## 9. ExecutionResult — output of `backend/execution/` (Vikash)

```
ExecutionResult = { ok: bool, resulting_version: int | null, reason: str | null }
```

---

## 10. REST request / response schemas

| Endpoint | Request | Success response | Codes |
|---|---|---|---|
| `GET /network/state` | — | `NetworkState` | 200 |
| `POST /network/reset` | — | `NetworkState` | 200 |
| `GET /telemetry` | — | `Telemetry` | 200 / 501 |
| `GET /faults` | — | `{ faults: [Fault] }` | 200 / 501 |
| `POST /faults` | `FaultRequest` | `{ fault: Fault, state: NetworkState }` | 201 / 404 / 422 / 501 |
| `DELETE /faults/{id}` | — | `{ state: NetworkState }` | 200 / 404 / 501 |
| `POST /recovery/diagnose` | — | `Diagnosis` | 200 / 501 / 502 |
| `POST /recovery/plan` | — | `{ diagnosis: Diagnosis, candidates: [RecoveryPlan] }` | 200 / 501 / 502 |
| `POST /recovery/run` | `RunRequest` (optional) | `RecoveryRunResult` | 200 / 500 |

```
RunRequest        = { auto_apply: bool = true }
PlanRequest       = { diagnosis_id: str | null }   # reserved; not yet consumed
CandidateResult   = { plan: RecoveryPlan, simulation: SimulationResult, safety: SafetyDecision }
RecoveryRunResult = { run_id, based_on_version: int, outcome: RunOutcome, message: str,
                      diagnosis: Diagnosis | null, candidates: [CandidateResult],
                      applied_plan_id: str | null, resulting_version: int | null, completed_at }
```

Expected recovery outcomes (`no_plan`, `no_safe_plan`, `diagnosis_failed`,
`approved_pending`, **and `error`**) are **not** HTTP errors — they are
`RecoveryRunResult.outcome` values with HTTP 200. Only an unexpected exception
escaping the pipeline becomes `500 internal_error`.

---

## 11. WebSocket event schemas

Envelope (every frame):

```
{ "type": WSEventType, "seq": int, "at": datetime, "version": int | null, "payload": { ... } }
```

| `type` | When | `payload` |
|---|---|---|
| `state` | on connect; after every `StateManager` mutation | `{ "state": NetworkState }` |
| `fault` | after a fault is injected / cleared | `{ "action": "injected", "fault": Fault }` or `{ "action": "cleared", "fault_id": str }` |
| `diagnosis` | during a run, after diagnosis | `{ "run_id": str, "diagnosis": Diagnosis }` |
| `simulation` | during a run, per candidate | `{ "run_id": str, "result": SimulationResult }` |
| `safety` | during a run, per candidate | `{ "run_id": str, "decision": SafetyDecision }` |
| `recovery` | run lifecycle | `{ "run_id": str, "stage": "started" | "completed", "result": RecoveryRunResult | null }` |
| `error` | pipeline surfaced an `error` outcome | `{ "run_id": str | null, "code": str, "message": str }` |

Rules: inbound frames ignored; the WS layer never mutates state; clients drop any
`state` frame with `version <= ` their current version.

---

## 12. Error schema

All non-2xx REST responses:

```
{ "error": { "code": str, "message": str, "details": dict | null } }
```

| `code` | HTTP | Meaning |
|---|---|---|
| `validation_error` | 422 | request body failed schema validation |
| `invalid_fault` | 422 | fault type/params invalid for target |
| `invalid_target` | 404 | referenced node/edge/service does not exist |
| `not_found` | 404 | referenced fault id / resource does not exist |
| `conflict` | 409 | state changed under the operation (version mismatch) |
| `pipeline_error` | 502 | a diagnosis/plan stage failed irrecoverably |
| `execution_error` | 500 | an approved plan failed to apply |
| `internal_error` | 500 | unexpected bug |
| `module_not_wired` | 501 | **TEMPORARY** — a teammate module is still a placeholder. Removed once all ports are wired. Not part of the frozen table |

---

## 13. Mutation primitives (`backend/state/mutations.py`)

`StateManager.apply_actions(mutations, reason)` accepts a list of these mechanical
field-write primitives — no domain semantics.

```
SetNodeFields    = { op: "set_node_fields",    node_id: str,    fields: dict[str, float|int|str|bool|list] }
SetEdgeFields    = { op: "set_edge_fields",    edge_id: str,    fields: dict[...] }
SetServiceFields = { op: "set_service_fields", service_id: str, fields: dict[...] }
SetActiveFaults  = { op: "set_active_faults",  fault_ids: list[str] }
```

Discriminated union on `op`. Rules: unknown target id → whole batch rejected;
`fields` with an unknown/out-of-range key → whole batch rejected (full
`NetworkState` re-validation); the batch is atomic — all or none; `version` bumps
once. `backend/faults/` emits these from a `Fault`; `backend/execution/` emits
them from an approved `RecoveryPlan`.

---

## 14. Ports (`backend/pipeline/ports.py`) — interface contracts

See `TRD.md` §5 for the full table. Signatures:

```
SeedSource.build_seed() -> NetworkState
NetworkModel.recompute_status(state) -> list[Mutation]
NetworkModel.resolve_path(service_id, state, *, avoid_nodes=None, avoid_edges=None, new_host=None) -> list[str] | None
TelemetrySource.derive(state) -> Telemetry
FaultInjector.inject(request, state) -> (Fault, list[Mutation])
FaultInjector.clear(fault_id, state) -> list[Mutation]
FaultInjector.active() -> list[Fault]
Diagnoser.diagnose(state, telemetry, active_faults) -> Diagnosis
RecoveryPlanner.plan(state, diagnosis) -> list[RecoveryPlan]
DigitalTwin.validate(state_copy, plan) -> SimulationResult
SafetyGate.evaluate(before, simulation, plan, policy) -> SafetyDecision
```

---

## 15. TEAM DECISION REQUIRED (values, not shapes)

| # | Decision | Needed by | Suggested default |
|---|---|---|---|
| D1 | `Telemetry.network_availability` formula | telemetry | fraction of services with `status == running` |
| D2 | Safety thresholds (availability floor / max latency increase / max node load / do warnings block) | safety | `>= 0.99` / `+20%` / `<= 0.90` / no |
| D3 | Seed topology final size + seed service set | network | 15–20 nodes, 3–4 services |
| D4 | Does `restore_node` require the underlying fault cleared first | twin, safety | yes |
| D5 | LLM provider + model; is the real LLM in demo scope | recovery | deterministic mock is the demo; LLM is a bonus |
| D6 | `auto_apply` default for `POST /recovery/run` | pipeline | `true` |

---

## 16. SHARED CONTRACT vs TEAMMATE INTERNAL

| Shared (this doc, Vikash) | Teammate internal (owner decides) |
|---|---|
| `NetworkState` / `NodeState` / `EdgeState` / `ServiceState` field sets; the `path` status rule | how topology/faults compute the field values (Sahil) |
| `Telemetry` field set | derivation math, availability formula (Sahil) |
| `Fault` / `FaultRequest` shape | param → field mapping, restore logic (Sahil) |
| `Diagnosis` shape | prompts, model, suspicion logic (Yyash) |
| closed `RecoveryAction` vocabulary, `RecoveryPlan` shape | candidate generation, selection, fallback (Yyash) |
| `SimulationResult` / `SimMetrics` shape | simulation method, action semantics in the twin (Sahil) |
| `SafetyDecision` / `Violation` shape, "approved iff no critical" | rule implementations, threshold values (Hrishi) |
| REST + WS envelopes, error schema, id patterns, versioning, mutation primitives, ports | — |
