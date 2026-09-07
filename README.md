# AEGIS

**Autonomous Network Recovery System.** AEGIS runs a simulated network and a
deterministic recovery loop over it:

> AI diagnoses the fault and *proposes* recovery plans → each plan is validated
> against a schema and simulated in a **Digital Twin** → a deterministic
> **Safety Gate** approves or rejects it → only an approved plan reaches the
> **Executor**, which is the single component that mutates network state.

The AI never touches the network directly. If no plan passes the Safety Gate,
nothing executes and the network is left unchanged.

## Run it

```sh
docker compose up -d --build      # backend :8000, frontend :5173
```

Open http://localhost:5173 and follow `docs/DEMO_SCRIPT.md` for the S1/S2/S3
demo.

Backend tests: `python -m pytest`

## Project structure

```text
aegis/
├── backend/
│   ├── api/            REST routes + WebSocket (transport only)
│   ├── pipeline.py     the recovery loop orchestrator
│   ├── diagnosis/      heuristic fault diagnosis
│   ├── recovery/       recovery planner
│   ├── simulation/     Digital Twin
│   ├── safety/         deterministic Safety Gate
│   ├── execution/      Executor (only state-mutation path)
│   ├── faults/         fault injector
│   ├── telemetry/      telemetry derivation
│   ├── state/          in-memory StateManager + seed
│   └── models/         Pydantic contracts
├── frontend/           React + Vite dashboard (backend-authoritative, no logic)
├── tests/
├── docs/
└── docker/
```
