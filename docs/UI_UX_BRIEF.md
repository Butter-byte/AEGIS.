# AEGIS — UI / UX Brief

**Primary owner:** Hrishi (Frontend / UI)
**This doc's author:** Vikash (Integration) — defines only *what the frontend
must expose and consume*. It does **not** design the frontend.

---

## Hrishi Ownership

> Frontend visual design, component architecture, interaction design, styling,
> layout, motion, and implementation are owned by Hrishi.
>
> Anything in this document phrased as a suggestion is exactly that — input for
> Hrishi to accept, adapt, or reject. The binding parts are: the product/UI
> goals (§1), the data and events the frontend consumes (§3), and the
> integration requirements (§5).

---

## 1. Product / UI goals (binding)

1. **Make the safety-gating story legible.** A viewer should see that the AI
   proposes, the twin tests, safety decides, and only then the network changes.
2. **One screen, real time.** The operator watches the network, injects a fault,
   triggers recovery, and sees the outcome without navigating away.
3. **Every state change is visible.** Faults, diagnosis, simulation results,
   safety decisions, and applied recoveries all surface as they happen.
4. **Rejections are first-class.** "No safe plan" with reasons is as clearly
   presented as a success.
5. **No hidden client state.** The UI reflects server-provided `NetworkState`;
   it never becomes a second source of truth (architectural invariant 11).

---

## 2. Information the frontend must expose (binding — content, not layout)

| Area | Must show |
|---|---|
| Network topology | nodes and links with their status (healthy / degraded / failed / quarantined; active / congested / failed) |
| Services | each service, its host node, and its status (running / degraded / down) |
| Telemetry | network availability, avg & max latency, total packet loss, counts of failed/degraded/quarantined nodes and congested/failed edges |
| Faults | list of active faults (type, target); controls to inject and clear |
| Diagnosis | summary, suspected nodes/edges/services, confidence, rationale |
| Candidate plans | per candidate: strategy label, ordered actions, rationale, source (llm/heuristic) |
| Simulation | per candidate: feasible?, predicted availability/latency/node-load, unreachable services, delta vs current |
| Safety decision | per candidate: approved?, list of violations (rule, detail, level) |
| Recovery run result | which plan was applied (or none), the outcome, resulting state version |
| State version | the current `NetworkState.version` (for the operator's orientation and debugging) |

---

## 3. Backend data & events the frontend consumes (binding)

### 3.1 REST (see `BACKEND_SCHEMA.md §8`)

| Call | When |
|---|---|
| `GET /network/state` | on load, on reconnect, as a fallback |
| `GET /telemetry` | on load; otherwise derive from streamed state or poll lightly |
| `GET /faults` | on load / after fault changes |
| `POST /faults`, `DELETE /faults/{id}` | operator injects / clears a fault |
| `POST /network/reset` | operator resets the simulation |
| `POST /recovery/diagnose` | operator wants diagnosis only |
| `POST /recovery/plan` | operator wants candidates without running |
| `POST /recovery/run` | operator runs the full cycle |

### 3.2 WebSocket `/ws` (see `BACKEND_SCHEMA.md §7`)

Envelope: `{ type, seq, at, version, payload }`. Event types:

| `type` | Frontend reaction (suggested) |
|---|---|
| `state` | replace the view model; re-render topology + telemetry. Drop if `version <= current`. |
| `fault` | update fault list; flash the affected element |
| `diagnosis` | show the diagnosis panel for the active run |
| `simulation` | add/update the candidate's simulation result |
| `safety` | add/update the candidate's safety decision |
| `recovery` | mark run started / completed; show final outcome |
| `error` | surface a non-blocking error notice |

**On connect:** the server sends one `state` event immediately — the frontend
should treat that as its initial sync.

**Inbound:** the frontend must not rely on sending anything over `/ws`; the
server ignores inbound frames.

---

## 4. Required UI states / events (binding)

The UI must have a defined presentation for each of:

- Network healthy / partially degraded / severely degraded.
- Fault being injected; fault active; fault cleared.
- Recovery run: idle → running (per-stage progress) → completed.
- Run outcomes: `applied`, `approved_pending`, `no_safe_plan`, `no_plan`,
  `diagnosis_failed`, `error` (from `RecoveryRunResult.outcome`).
- Candidate plan: proposed → simulated → approved / rejected.
- WebSocket connected / reconnecting / disconnected.
- Backend error notice (from `error` events and non-2xx REST responses).

---

## 5. Integration requirements (binding)

| # | Requirement |
|---|---|
| U1 | All backend access goes through `frontend/services/api.ts` (REST) and `frontend/services/socket.ts` (WS). No `fetch`/WS calls elsewhere. |
| U2 | The frontend holds a single view model, sourced entirely from the server. It contains no recovery, safety, or diagnosis logic. |
| U3 | The topology rendered is the one in `NetworkState` — never a hardcoded topology. Node/edge ids and statuses come from the server. |
| U4 | The frontend applies the stale-frame rule: ignore any `state` event with `version <= ` the current version. |
| U5 | The frontend degrades gracefully if `/ws` drops: fall back to `GET /network/state` (+ `GET /telemetry`) until reconnected. |
| U6 | Types for all consumed models are generated from or kept in sync with `BACKEND_SCHEMA.md` (single shared contract). |
| U7 | The frontend never assumes a recovery run mutated state — it reads `resulting_version` / waits for a `state` event. |

---

## 6. Suggestions to inform Hrishi (non-binding)

- A single dashboard with: topology graph (largest area), telemetry strip,
  fault controls, and a recovery timeline/log that fills in as `diagnosis` →
  `simulation` → `safety` → `recovery` events arrive.
- Color nodes/edges by status; badge quarantined nodes distinctly (they matter
  for safety rules).
- Show candidate plans as a small comparison list (availability, latency,
  approved?) so the "pick the best safe one" logic is visible to the audience.
- For `no_safe_plan`, show the rejection `violations` prominently — this is the
  moment that sells the safety concept.
- The existing `origin/frontend` dashboard (React + `@xyflow/react`) is a
  reasonable starting shell; its hardcoded 5-node topology and mocked telemetry
  must be replaced with live data (see INFORM Hrishi in `IMPLEMENTATION_PLAN.md`).

---

## 7. Out of scope for the MVP UI

Authentication screens · settings/preferences · topology editing · historical
charts / time travel · multiple concurrent runs · theming beyond one look ·
mobile layout · i18n.
