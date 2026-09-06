# AEGIS — Product Requirements Document (PRD)

**Product:** AEGIS — Safety-Gated Autonomous Network Recovery
**Owner of this doc:** Vikash (System Architect + Integration Lead)
**Type:** 3-day hackathon MVP
**Status:** Draft for team ratification

This document describes **what** AEGIS does and **why**. It is
technology-independent where possible. For teammate-owned areas it states the
required product behavior only, not the implementation.

---

## 1. Problem

Modern networks fail in ways that are fast, cascading, and stressful to
diagnose. Human operators under pressure either act too slowly or apply changes
whose side effects they cannot fully predict. Fully autonomous remediation is
attractive but dangerous: an automated system that can directly reconfigure the
network can also directly break it.

**AEGIS demonstrates a middle path:** an AI proposes recovery strategies, a
simulation predicts their effect, and a deterministic safety layer decides
whether any proposed strategy is allowed to touch the network. The AI advises;
it never acts.

---

## 2. Product vision

> A network that diagnoses its own failures, imagines several ways to fix
> itself, proves which fix is safe, and applies only that one — with a human able
> to watch every step.

---

## 3. Users & personas

| Persona | Goal | How they use AEGIS |
|---|---|---|
| **Network operator (primary)** | Restore service quickly without making things worse | Watches the live network, injects/observes a fault, triggers recovery, sees why a plan was approved or rejected |
| **Reliability reviewer** | Trust that automation is bounded | Inspects the safety decision and its reasons |
| **Hackathon judge / demo audience** | Understand the concept in 3 minutes | Watches a single scripted fault → recovery cycle on the dashboard |

There is no authentication and no multi-user model in the MVP — a single operator
session.

---

## 4. Core product flow (black-box)

```
Healthy network
  → operator injects a fault
  → telemetry degrades (visible on dashboard)
  → operator requests recovery
  → AI diagnoses the failure
  → AI proposes several candidate recovery strategies
  → each candidate is simulated against a digital twin
  → a deterministic safety engine approves or rejects each candidate
  → the best safe candidate is applied to the live network
  → telemetry recovers (visible on dashboard)
  → if no candidate is safe, nothing is applied and the operator is told why
```

Every step is observable in real time.

---

## 5. Functional requirements

### 5.1 Network observability
- FR1: The system maintains a single authoritative model of the network's
  current state (nodes, links, hosted services, health metrics).
- FR2: The operator can view the full current network state at any time.
- FR3: The system exposes derived telemetry: availability, latency, packet loss,
  counts of failed/degraded/quarantined elements.
- FR4: State and telemetry changes are pushed to the operator's view in real
  time.

### 5.2 Fault injection
- FR5: The operator can inject a fault of a defined type against a specific node
  or link (e.g. kill a node, degrade a node, cut a link, congest a link, apply a
  traffic spike).
- FR6: An injected fault immediately and visibly changes network state and
  telemetry.
- FR7: The operator can list active faults and clear a fault, returning affected
  elements toward normal.
- FR8: Invalid fault requests (unknown target, wrong target type) are rejected
  with a clear reason and no state change.

### 5.3 Diagnosis
- FR9: On request, the system produces a diagnosis of the current failure: a
  summary, the suspected nodes/links/services, a confidence level, and a
  human-readable rationale.
- FR10: Diagnosis is advisory only — it never changes the network.
- FR11: If the AI is unavailable or produces unusable output, the system still
  returns a usable diagnosis via a deterministic fallback, or clearly reports
  that diagnosis failed.

### 5.4 Recovery planning
- FR12: The system produces one or more candidate recovery plans. Each plan is an
  ordered list of actions drawn from a fixed, restricted vocabulary (reroute,
  drain node, restore node, migrate service, quarantine node, reset link).
- FR13: Plans never contain free-form commands, scripts, device configuration, or
  code. The action vocabulary is closed.
- FR14: A malformed or out-of-vocabulary plan is discarded; the operator is told
  how many candidates were valid.
- FR15: If no valid plan can be produced, the system says so and changes nothing.

### 5.5 Simulation (digital twin)
- FR16: Each candidate plan is evaluated against an isolated copy of the current
  network state. Simulation never affects the live network.
- FR17: Simulation reports, per plan: whether the plan is feasible, and the
  predicted availability, latency, node load, and any services left unreachable.
- FR18: Multiple candidate plans can be compared on these predicted metrics.

### 5.6 Safety decision
- FR19: A deterministic safety engine evaluates each simulated plan and returns
  an approve/reject decision with explicit reasons for any rejection.
- FR20: The same plan and simulation always produce the same safety decision.
- FR21: The safety decision does not depend on the AI's reasoning or text — only
  on structured metrics and rules.
- FR22: Example rejection conditions (exact thresholds are a team decision):
  predicted availability below a floor; latency degradation beyond a limit; a
  plan that uses a quarantined node; a plan that leaves a service with no valid
  path; a plan the twin found infeasible.

### 5.7 Execution
- FR23: Only a safety-approved plan may be applied to the live network.
- FR24: The AI cannot apply a plan. Application happens only through the
  execution path after approval.
- FR25: When a plan is applied, the live network state updates atomically and the
  change is pushed to the operator's view.
- FR26: If application fails, the live state is left unchanged and the failure is
  reported.

### 5.8 Recovery run (the whole cycle)
- FR27: The operator can trigger the full cycle (diagnose → plan → simulate →
  decide → apply) with one action.
- FR28: The result reports: the diagnosis, every candidate with its simulation
  and safety decision, which plan (if any) was applied, and the resulting state
  version.
- FR29: Every stage of the run is streamed to the operator's view as it happens.

### 5.9 Reset
- FR30: The operator can reset the simulation to a clean seed topology at any
  time.

---

## 6. Non-functional requirements

| # | Requirement |
|---|---|
| NFR1 | A full recovery run (excluding external LLM latency) completes in a few seconds. |
| NFR2 | The demo runs end-to-end with no live LLM dependency (deterministic fallback). |
| NFR3 | The whole system runs locally: one backend process, one frontend dev server. No databases, queues, or cloud services. |
| NFR4 | State is in-memory; a restart yields a fresh seed. No persistence is required for the MVP. |
| NFR5 | The operator can always see the current state and the reason behind the latest safety decision. |
| NFR6 | The system never applies an unapproved change, even under AI failure or malformed output. |

---

## 7. Product invariants (must always hold)

1. There is exactly one authoritative network state.
2. The AI is advisory. It never modifies or controls the network.
3. Recovery actions come from a fixed, restricted vocabulary — never arbitrary
   commands.
4. Simulation cannot affect the live network.
5. The safety engine is deterministic and independent of the AI's reasoning.
6. Only a safety-approved plan is ever applied.
7. Every state change and decision is observable in real time.

---

## 8. Demo scenario (acceptance narrative)

1. Dashboard shows a healthy topology, availability ~100%.
2. Operator clicks "Kill Node" on a node carrying a service.
3. Telemetry drops; the node and its links show failed; a service shows down.
4. Operator clicks "Run Recovery".
5. The run streams: diagnosis appears → 2–3 candidate plans → each simulated →
   each gets a safety decision.
6. One safe plan (e.g. migrate the service + reroute) is applied.
7. Telemetry recovers; the dashboard shows the new healthy state.
8. Operator injects a second, unrecoverable fault, runs recovery, and sees
   "No safe recovery plan" with the rejection reasons — and the network
   unchanged.

**MVP is accepted when this narrative works reliably without a live LLM.**

---

## 9. Out of scope (MVP)

- Authentication, user accounts, roles, multi-operator sessions.
- Persistence, history, audit log beyond the current session.
- Real network hardware, real SDN controllers, real routing protocols.
- Editable topologies / a topology builder (one fixed seed only).
- Multiple simultaneous recovery runs.
- Reinforcement learning, custom neural networks, model training.
- Kubernetes, Kafka, Redis, PostgreSQL, cloud infrastructure, microservices.
- Cost-optimal or multi-step-lookahead planning.
- Mobile app; internationalization; theming beyond a single look.

---

## 10. Teammate-owned product areas (behavior only)

The following describe **required product behavior**. How they are built is owned
by the named person and specified in their own work, not here.

- **Network simulation, topology, telemetry, fault injection (Sahil):** must
  provide a believable small network whose state and telemetry respond visibly
  and consistently to faults and recovery actions.
- **Digital twin (Sahil):** must predict the effect of a candidate plan on an
  isolated copy and report comparable metrics, without touching the live network.
- **AI diagnosis & recovery planning (Yyash):** must produce a useful diagnosis
  and a small set of candidate plans expressed only in the restricted action
  vocabulary, with graceful behavior on failure.
- **Safety engine (Hrishi):** must deterministically approve or reject each
  simulated plan with clear reasons, independent of the AI's text.
- **Frontend (Hrishi):** must make the whole cycle observable and let the
  operator inject faults and trigger recovery. See `UI_UX_BRIEF.md`.

---

## 11. Success metrics (hackathon)

| Metric | Target |
|---|---|
| Demo narrative (§8) runs without manual intervention | yes |
| Runs without a live LLM | yes |
| Unapproved change ever reaches the live network | never |
| Time from "Run Recovery" to applied plan (fallback) | < 5 s |
| Judges can restate the safety-gating concept after the demo | yes |
