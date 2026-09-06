# AEGIS Frontend Integration Contract

This document describes the current backend contract for frontend WebSocket and fault integration.

## WebSocket Connection

Connect to:

```text
ws://localhost:8000/ws
```

Every message uses this envelope:

```json
{
  "type": "state",
  "seq": 0,
  "at": "2026-09-06T16:00:00Z",
  "version": 1,
  "payload": {}
}
```

Fields:

- `type`: `state`, `fault`, `diagnosis`, `simulation`, `safety`, `recovery`, or `error`
- `seq`: monotonically increasing counter for the connection
- `at`: UTC timestamp
- `version`: related network-state version, or `null`
- `payload`: event-specific object

The server sends one initial `state` event when the WebSocket connects. Incoming client messages are ignored and never mutate the network.

## Event Types

### `state`

Sent on connection and after every committed state mutation.

```json
{
  "type": "state",
  "seq": 0,
  "version": 1,
  "payload": {
    "state": {
      "version": 1,
      "updated_at": "2026-09-06T16:00:00Z",
      "nodes": {},
      "edges": [],
      "services": {},
      "active_fault_ids": []
    }
  }
}
```

`NetworkState` contains `nodes`, `edges`, `services`, and `active_fault_ids`.

### `diagnosis`

Emitted during `POST /recovery/run`.

```json
{
  "type": "diagnosis",
  "version": 1,
  "payload": {
    "run_id": "run-a1b2c3d4",
    "diagnosis": {
      "id": "dx-a1b2c3d4",
      "created_at": "2026-09-06T16:00:00Z",
      "based_on_version": 1,
      "summary": "kill_node at N7",
      "suspected_nodes": ["N7"],
      "suspected_edges": [],
      "suspected_services": ["svc-payment"],
      "confidence": 0.9,
      "rationale": "Telemetry reports 1 failed and 0 quarantined nodes."
    }
  }
}
```

### `simulation`

One event is emitted for each candidate recovery plan.

```json
{
  "type": "simulation",
  "version": 1,
  "payload": {
    "run_id": "run-a1b2c3d4",
    "result": {
      "plan_id": "plan-a1b2c3d4",
      "based_on_version": 1,
      "feasible": true,
      "infeasible_reason": null,
      "metrics": {
        "availability": 1.0,
        "avg_latency": 12.0,
        "max_latency": 12.0,
        "worst_node_load": 0.45,
        "unreachable_services": [],
        "path_count": 105
      },
      "delta": {
        "availability": 0.0,
        "avg_latency": 0.0,
        "max_latency": 0.0
      },
      "errors": [],
      "computed_at": "2026-09-06T16:00:00Z"
    }
  }
}
```

### `safety`

One event is emitted for each simulated plan.

```json
{
  "type": "safety",
  "version": 1,
  "payload": {
    "run_id": "run-a1b2c3d4",
    "decision": {
      "plan_id": "plan-a1b2c3d4",
      "based_on_version": 1,
      "approved": true,
      "violations": [],
      "evaluated": {
        "availability": 1.0
      },
      "policy_version": "p0-scaffold",
      "decided_at": "2026-09-06T16:00:00Z"
    }
  }
}
```

### `recovery`

The pipeline emits a `started` event:

```json
{
  "type": "recovery",
  "version": 1,
  "payload": {
    "run_id": "run-a1b2c3d4",
    "stage": "started",
    "result": null
  }
}
```

It emits a `completed` event at the end:

```json
{
  "type": "recovery",
  "version": 2,
  "payload": {
    "run_id": "run-a1b2c3d4",
    "stage": "completed",
    "result": {
      "run_id": "run-a1b2c3d4",
      "based_on_version": 1,
      "outcome": "applied",
      "message": "applied plan plan-a1b2c3d4",
      "diagnosis": {},
      "candidates": [],
      "applied_plan_id": "plan-a1b2c3d4",
      "resulting_version": 2,
      "completed_at": "2026-09-06T16:00:00Z"
    }
  }
}
```

Possible outcomes:

```text
applied
approved_pending
no_safe_plan
no_plan
diagnosis_failed
error
```

### `error`

Emitted when the recovery pipeline ends with `outcome: "error"`.

```json
{
  "type": "error",
  "version": 1,
  "payload": {
    "run_id": "run-a1b2c3d4",
    "code": "pipeline_error",
    "message": "..."
  }
}
```

### `fault`

`fault` is an allowed event type, but the backend does not currently emit a dedicated `fault` WebSocket event.

Fault injection automatically emits a `state` event because it mutates the canonical `StateManager`. The frontend should detect the fault through `state.active_fault_ids` and changed node or edge status.

## Fault REST API

### Inject a fault

```http
POST /faults
Content-Type: application/json
```

Request:

```json
{
  "type": "kill_node",
  "target": "N7",
  "params": {}
}
```

Supported fault types:

```text
kill_node
degrade_node
overload_node
cut_edge
congest_edge
traffic_spike
```

Example response, HTTP `201`:

```json
{
  "id": "flt-a1b2c3d4",
  "type": "kill_node",
  "target": "N7",
  "params": {},
  "created_at": "2026-09-06T16:00:00Z"
}
```

### List active faults

```http
GET /faults
```

Returns an array of active fault objects.

### Clear a fault

```http
DELETE /faults/{fault_id}
```

Example response:

```json
{
  "cleared": "flt-a1b2c3d4"
}
```

Clearing a fault also causes a `state` WebSocket event.

## Recovery REST API

### Run the complete recovery pipeline

```http
POST /recovery/run
Content-Type: application/json
```

Request:

```json
{
  "auto_apply": true
}
```

This endpoint emits the `recovery`, `diagnosis`, `simulation`, `safety`, and final `recovery` events.

### Direct diagnosis

```http
POST /recovery/diagnose
```

Returns a `Diagnosis` response but does not emit a WebSocket diagnosis event by itself.

### Direct planning

```http
POST /recovery/plan
Content-Type: application/json
```

Optional request body:

```json
{
  "diagnosis_id": "dx-a1b2c3d4"
}
```

Returns a diagnosis and candidate recovery plans but does not emit WebSocket events by itself.

## Normal Recovery Event Sequence

```text
POST /faults
  -> state event

POST /recovery/run
  -> recovery: started
  -> diagnosis
  -> simulation (one per candidate)
  -> safety (one per candidate)
  -> state event if the approved plan is applied
  -> recovery: completed
```

The `state` event from approved execution normally appears before the final `recovery: completed` event because execution commits through `StateManager`.
