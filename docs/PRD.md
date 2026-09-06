# AEGIS — Product Requirements Document (PRD)

**Product:** AEGIS — Safety-Gated Autonomous Network Recovery (simulated)
**Doc owner:** Vikash (System Architect + Integration Lead)
**Type:** hackathon MVP · **Status:** draft for team ratification

This document describes **what** AEGIS does and **why**. Teammate-owned areas are
stated as *required behaviour*, not implementation. Field-level contracts live in
`BACKEND_SCHEMA.md` (the source of truth); architecture in `TRD.md`.

---

## 1. Problem

Networks fail fast and in cascades. Human operators under pressure act too slowly
or apply changes whose side effects they cannot predict. Fully autonomous
remediation is attractive but dangerous: automation that can reconfigure the
network can also break it.

**AEGIS demonstrates a middle path.** An AI proposes recovery strategies; a
digital twin predicts their effect; a deterministic safety gate decides whether
any proposal may touch the network. The AI advises — it never acts.

## 2. Vision

> A network that diagnoses its own failures, imagines several ways to fix itself,
> proves which fix is safe, applies only that one — with a human watching every step.

## 3. Users

| Persona | Goal | Use of AEGIS |
|---|---|---|
| Network operator (primary) | Restore service without making things worse | Watch the network, inject/observe a fault, trigger recovery, see why a plan was approved or rejected |
| Reliability reviewer | Trust that automation is bounded | Inspect the safety decision and its reasons |
| Hackathon judge | Understand the concept in 3 minutes | Watch one scripted fault → recovery cycle |

Single operator session. No authentication, no multi-user model.

## 4. Core product flow (black box)

```
Healthy network
  → operator injects a fault
  → telemetry + state degrade (visible)
  → operator requests recovery
  → AI diagnoses the failure
  → AI proposes candidate recovery plans (closed action vocabulary)
  → each candidate is validated against a Digital Twin
  → a deterministic Safety Gate approves or rejects each candidate
  → the best safe candidate is applied to the live network
  → telemetry + state recover (visible)
  → if no candidate is safe, nothing is applied and the operator is told why
```

Every step is observable in real time over a WebSocket.

## 5. MVP capabilities

Each capability has a **purpose** and an **acceptance criterion** (AC). The list
is 16 items — sized to a hackathon, not padded.

| # | Capability | Purpose | Acceptance criterion |
|---|---|---|---|
| C1 | **Authoritative network state** | One source of truth for the whole system | `GET /network/state` returns a single versioned `NetworkState`; no other store is authoritative |
| C2 | **Deterministic seed topology** *(Sahil)* | Reproducible demos and tests | Same build ⇒ identical topology; 15–30 nodes, connected, ≥3 services |
| C3 | **Topology graph + pathfinding** *(Sahil)* | Routing/reroute decisions | Given a service + hazards, returns a viable node path or "none" |
| C4 | **Derived telemetry** *(Sahil)* | Operator-facing health view | `GET /telemetry` returns availability, latency, loss, and node/edge counts derived purely from state |
| C5 | **Real-time state streaming** *(Vikash)* | Live dashboard | On WS connect the client gets the current state; every mutation is broadcast within 250 ms |
| C6 | **Fault injection** *(Sahil + Vikash glue)* | Create demo failures | `POST /faults` with a closed `FaultType` visibly changes state + telemetry; invalid target → 4xx, no change |
| C7 | **Fault clearing** *(Sahil + Vikash glue)* | Reset a failure | `DELETE /faults/{id}` moves affected elements back toward nominal |
| C8 | **Fault detection** *(Sahil)* | The system notices the failure | After injection, telemetry availability drops and the affected service's status changes |
| C9 | **AI diagnosis** *(Yyash; deterministic mock first)* | Explain the failure | `POST /recovery/diagnose` returns a `Diagnosis` (summary, suspects, confidence, rationale); never mutates state |
| C10 | **Recovery planning** *(Yyash; deterministic mock first)* | Propose fixes | `POST /recovery/plan` returns 1..N `RecoveryPlan`s drawn only from the closed action vocabulary |
| C11 | **AI-output schema gate** *(Vikash)* | Structurally enforce "no AI output touches the network" | A malformed / out-of-vocabulary / unknown-id plan is rejected before the twin; run reports how many candidates were valid |
| C12 | **Digital Twin validation** *(Sahil)* | Predict a plan's effect safely | Each plan is simulated on an isolated copy; result reports feasibility + predicted metrics; live state unchanged |
| C13 | **Deterministic Safety Gate** *(Hrishi)* | Decide what may execute | Same (state, simulation, plan, policy) ⇒ same `SafetyDecision`; no LLM; `approved` iff no critical violation |
| C14 | **Safety-gated execution** *(Vikash)* | Apply only approved plans, atomically | Execution refuses any plan without an approved decision for the current version; applies as one atomic version bump |
| C15 | **Full recovery pipeline** *(Vikash)* | One-click autonomous cycle | `POST /recovery/run` runs observe→diagnose→plan→twin→safety→execute and returns an honest `RunOutcome` |
| C16 | **Three scripted demo scenarios** *(Sahil + all)* | Repeatable demo | Each scenario runs to a known outcome: (1) safe reroute, (2) multi-action recovery, (3) unsafe plan rejected |

**Cross-cutting:** an automated test suite (Vikash owns the architecture/
integration tests) is a first-class deliverable, not a capability line item.

## 6. Non-functional requirements

| # | Requirement |
|---|---|
| NFR1 | A full recovery run (deterministic modules, no LLM) completes in < 5 s |
| NFR2 | The demo runs end-to-end with no live LLM dependency |
| NFR3 | Runs locally: one backend process, one frontend dev server. No DB, queue, or cloud |
| NFR4 | State is in-memory; restart ⇒ fresh seed. No persistence required |
| NFR5 | The operator can always see current state and the reason behind the latest safety decision |
| NFR6 | An unapproved change never reaches the live network, even under AI failure or malformed output |

## 7. Product invariants (always hold)

1. Exactly one authoritative `NetworkState`.
2. The AI is advisory — it never mutates or controls the network.
3. Recovery actions come from a fixed, closed vocabulary — never arbitrary commands.
4. The Digital Twin cannot affect the live network.
5. The Safety Gate is deterministic and independent of the AI's reasoning/text.
6. Only a safety-approved plan is ever applied.
7. Every state change and decision is observable in real time.
8. **Service health is judged against the service's *assigned* path.** An
   alternate physical path existing does **not** heal a service — only an
   executed `reroute`/`migrate` does. (See `BACKEND_SCHEMA.md` §2.3.)

## 8. Demo narrative (acceptance)

1. Dashboard shows a healthy topology, availability ≈ 100%.
2. Operator injects a fault on a node/link carrying a service.
3. Telemetry drops; the element shows failed; the service shows down.
4. Operator clicks **Run Recovery**.
5. The run streams: diagnosis → candidate plans → each twin-validated → each
   safety-decided.
6. One safe plan is applied.
7. Telemetry recovers; the dashboard shows the new healthy state.
8. Operator injects a second failure whose only proposed fix is unsafe, runs
   recovery, and sees **"no safe recovery plan"** with the rejection reasons —
   network unchanged.

**MVP is accepted when this narrative runs reliably without a live LLM.**

## 9. Out of scope (MVP)

Auth / accounts / multi-operator · persistence / history / audit log · real
hardware / SDN / routing protocols · topology editor · multiple concurrent runs ·
RL / model training · Kubernetes / Kafka / Redis / Postgres / cloud · cost-optimal
or multi-step-lookahead planning · mobile · i18n · theming beyond one look.

## 10. Ownership (behaviour only — see `TRD.md` for the code map)

- **Sahil:** believable simulated network; telemetry; fault injection; Digital Twin.
- **Yyash:** useful diagnosis; candidate plans in the closed vocabulary; graceful failure.
- **Hrishi:** deterministic Safety Gate; the operations dashboard (`UI_UX_BRIEF.md`).
- **Vikash:** architecture, shared contracts, state authority, API/WS, pipeline,
  execution, integration + E2E tests.
