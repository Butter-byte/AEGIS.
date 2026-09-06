# AEGIS — UI / UX Brief

**Primary owner:** Hrishi (Frontend / UI)
**This doc's author:** Vikash (Integration) — defines only *what the frontend
consumes and must expose*. It does **not** design the frontend, and **no UI is
implemented as part of Vikash's scope.**

---

## Ownership

> Frontend visual design, component architecture, interaction design, styling,
> layout, motion, state handling, and implementation are **owned by Hrishi**.
>
> `frontend/` does not exist in the repository yet — Hrishi creates it (Vite +
> React + TypeScript + `@xyflow/react`). Nothing in Vikash's scope adds frontend
> code.
>
> The **binding** parts of this document are: the product/UI goals (§1), the data
> and events the frontend consumes (§3), and the integration requirements (§5).
> Everything phrased as a suggestion (§6) is input for Hrishi to accept or reject.

---

## 1. Product / UI goals (binding)

1. **Make the safety-gating story legible.** A viewer sees: the AI proposes, the
   twin tests, safety decides, and only then the network changes.
2. **One screen, real time.** Watch the network, inject a fault, trigger
   recovery, see the outcome without navigating away.
3. **Every state change is visible** — faults, diagnosis, simulation results,
   safety decisions, applied recoveries — as they happen.
4. **Rejections are first-class.** "No safe plan" with reasons is presented as
   clearly as a success.
5. **No hidden client state.** The UI reflects server-provided `NetworkState`;
   it never becomes a second source of truth (invariant 9).

## 2. Information the frontend must expose (binding — content, not layout)

| Area | Must show |
|---|---|
| Topology | nodes + links with status (healthy / degraded / failed / quarantined ; active / congested / failed) |
| Services | each service, its host node, **its assigned path**, and status (running / degraded / down) |
| Telemetry | availability, avg & max latency, total packet loss, counts of failed/degraded/quarantined nodes and congested/failed edges |
| Faults | active faults (type, target); controls to inject and clear |
| Diagnosis | summary, suspected nodes/edges/services, confidence, rationale, source |
| Candidate plans | per candidate: strategy label, ordered actions, rationale, source |
| Simulation | per candidate: feasible?, predicted availability/latency/worst-node-load, unreachable services, delta |
| Safety decision | per candidate: approved?, violations (rule, detail, level), policy version |
| Recovery run result | which plan was applied (or none), outcome, resulting version |
| State version | current `NetworkState.version` |

## 3. Backend data & events the frontend consumes (binding)

### 3.1 REST — see `BACKEND_SCHEMA.md` §10

`GET /network/state` · `GET /telemetry` · `GET /faults` · `POST /faults` ·
`DELETE /faults/{id}` · `POST /network/reset` · `POST /recovery/diagnose` ·
`POST /recovery/plan` · `POST /recovery/run`

### 3.2 WebSocket `/ws` — see `BACKEND_SCHEMA.md` §11

Envelope: `{ type, seq, at, version, payload }`.

| `type` | Frontend reaction (suggested) |
|---|---|
| `state` | replace the view model; re-render. Drop if `version <= current` |
| `fault` | update fault list; flash the affected element |
| `diagnosis` | show the diagnosis panel for the active run |
| `simulation` | add/update the candidate's simulation result |
| `safety` | add/update the candidate's safety decision |
| `recovery` | mark run started / completed; show final outcome |
| `error` | surface a non-blocking error notice |

**On connect:** the server sends one `state` frame — treat it as the initial sync.
**Inbound:** the frontend must not rely on sending anything over `/ws`.

## 4. Required UI states (binding — must each have a defined presentation)

- Network healthy / partially degraded / severely degraded.
- Fault: injecting → active → cleared.
- Recovery run: idle → running (per-stage) → completed.
- Run outcomes: `applied`, `approved_pending`, `no_safe_plan`, `no_plan`,
  `diagnosis_failed`, `error`.
- Candidate: proposed → simulated → approved / rejected.
- WebSocket: connected / reconnecting / disconnected.
- Backend error notice (from `error` events and non-2xx REST).
- A backend endpoint returning `501 module_not_wired` (during development).

## 5. Integration requirements (binding)

| # | Requirement |
|---|---|
| U1 | All backend access goes through one REST client module and one socket module. No `fetch`/WS calls elsewhere |
| U2 | One client view model, sourced entirely from the server. No recovery / safety / diagnosis logic in the frontend |
| U3 | The rendered topology is the one in `NetworkState` — never hardcoded. Node/edge ids and statuses come from the server |
| U4 | Apply the stale-frame rule: ignore any `state` event with `version <= current` |
| U5 | Degrade gracefully if `/ws` drops: fall back to `GET /network/state` (+ `GET /telemetry`) until reconnected |
| U6 | TypeScript types for consumed models are kept in sync with `BACKEND_SCHEMA.md` |
| U7 | Never assume a recovery run mutated state — read `resulting_version` / wait for a `state` event |

## 6. Suggestions (non-binding — for Hrishi)

- Dark network-operations aesthetic: near-black ground; status colours
  green/amber/red; a distinct badge for **quarantined** and for **protected**
  nodes (both matter for safety rules).
- Layout: topology graph dominant (left), stacked cards right (Telemetry →
  Active Faults → Diagnosis → Recovery Plan → Twin Result → Safety Gate →
  Execution), event timeline along the bottom filling in as events arrive.
- Show candidate plans as a small comparison list (availability, latency,
  approved?) so "pick the best safe one" is visible to the audience.
- For `no_safe_plan`, feature the rejection `violations` prominently — that is
  the moment that sells the concept.
- Render each service's assigned `path` as a highlighted route on the graph so
  the "alternate path doesn't auto-heal" behaviour is visible.

## 7. Out of scope for the MVP UI

Auth screens · settings · topology editing · historical charts / time travel ·
multiple concurrent runs · theming beyond one look · mobile · i18n.
