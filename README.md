# AEGIS

**Safety-Gated Autonomous Network Recovery** (on a simulated network).

An AI proposes recovery strategies; a Digital Twin predicts their effect; a
deterministic Safety Gate decides whether any proposal may touch the network.
**No AI output touches the network directly.**

```
Simulated Network → Telemetry → State → AI Diagnosis → Recovery Planner
  → Digital Twin Validation → Deterministic Safety Gate → Execute → Updated State → Feedback
```

## Status

Phase 0 + Phase 1 complete — **Vikash's architecture / integration backbone**:
shared contracts, authoritative state, pipeline orchestration, execution
boundary, REST + WebSocket, and the test suite. Teammate modules
(`backend/network`, `telemetry`, `faults`, `twin`, `diagnosis`, `recovery`,
`safety`, and `frontend/`) are placeholders with defined interfaces and
deterministic fakes. See `docs/IMPLEMENTATION_PLAN.md`.

## Layout

```
backend/
  models/      shared Pydantic contracts (leaf — the integration boundary)   [Vikash]
  state/       StateManager: the only authoritative writer                   [Vikash]
  pipeline/    orchestrator + ports (Protocols for teammate modules)         [Vikash]
  execution/   applies ONLY safety-approved plans, atomically                [Vikash]
  events/      WebSocket broadcaster                                         [Vikash]
  api/         REST routes + /ws + error mapping + composition root          [Vikash]
  network/ telemetry/ faults/ twin/       placeholders                       [Sahil]
  diagnosis/ recovery/                     placeholders                      [Yyash]
  safety/                                  placeholder                       [Hrishi]
  scenarios/                               placeholder                       [Sahil + all]
tests/         model / contract / state / api / ws / pipeline / boundary / E2E [Vikash]
docs/          PRD · TRD · APP_FLOW · UI_UX_BRIEF · BACKEND_SCHEMA · IMPLEMENTATION_PLAN
frontend/      NOT YET CREATED                                               [Hrishi]
```

`docs/BACKEND_SCHEMA.md` is the frozen source of truth for every cross-module shape.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

.venv/bin/pytest                                        # test suite
.venv/bin/uvicorn backend.main:app --reload --port 8000 # dev server
```

With no teammate modules wired, `GET /network/state`, `POST /network/reset` and
`/ws` work against a scaffold seed; other endpoints return `501 module_not_wired`
until their owner wires the module in `backend/main.py`.

## Ground rules

- One owner per work session — do not implement another teammate's module (see
  `docs/IMPLEMENTATION_PLAN.md`).
- Contract changes go through `docs/BACKEND_SCHEMA.md` first.
- Git / GitHub operations are performed **manually by the team**.
