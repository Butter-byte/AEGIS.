# Aegis AI Diagnosis + Recovery Planner Guide

This guide records the design decisions behind the hackathon prototype.

## Architecture boundary

`Simulator -> Anomaly Detector -> Diagnosis Engine -> Recovery Planner -> Plan Ranker -> Summary Generator -> Digital Twin -> Safety Engine -> Executor`

The AI-side modules diagnose and propose. They never send device commands. The Digital Twin predicts consequences; the Safety Engine authorizes only bounded, policy-compliant actions.

## Network metrics

| Metric | Normal guide | Warning | Critical | Typical meaning when abnormal |
|---|---:|---:|---:|---|
| CPU usage | Below 60% | 75%+ | 90%+ | Router/firewall processing overload, traffic spike, control-plane storm |
| Memory usage | Below 70% | 80%+ | 90%+ | Session pressure, route-table growth, memory leak |
| Available memory | Device-specific | - | Below 256 MB | Immediate memory pressure despite a misleading percentage |
| Latency | Route baseline | 100 ms+ or 2x baseline | 200 ms+ | Congestion, long/bad route, packet retransmission, overloaded device |
| Packet loss | Near 0% | 1%+ | 2%+ | Link fault, congestion, queue drops, device overload |
| Bandwidth utilization | Below 70-80% | 80%+ | 90%+ | Capacity pressure; congestion when combined with loss/drops/delay |
| Throughput | Matches route/application baseline | Sudden drop | Persistent low delivery | Loss, bottleneck, rate-limit, path failure |
| Node health | healthy | degraded | unhealthy/unreachable | Device/service availability problem |

A single metric is a clue. A correlated timeline of metrics, topology, events, and service impact is a diagnosis.

## Input contract

Use `sample_telemetry.json` as the simulator example and `telemetry_schema.json` as the formal contract. Every payload needs:

- version and generation timestamp;
- incident context;
- one or more nodes, each with CPU, memory, network telemetry, and interfaces when applicable;
- links, services, and recent events when available;
- explicit data-quality information.

Use UTC ISO-8601 timestamps and stable IDs such as `router-r3`. Do not include passwords, tokens, or private keys.

## Rule-based anomaly detection

The detector reports explicit findings with target, measured value, threshold, severity, and evidence.

- Router overload: CPU >= 90% plus at least one forwarding symptom such as high latency, loss, or a saturated interface.
- Link fault: loss/errors or an enabled-but-down interface while device CPU remains below 75%.
- Congestion: interface utilization >= 90% plus packet loss or drops.
- Memory issue: memory >= 90% or available memory below 256 MB.
- Dead node: health is `unhealthy` or `unreachable`.

## Root-cause hypotheses

| Pattern | Hypothesis | Important confirmation check |
|---|---|---|
| CPU >= 90% + latency/loss/utilization | `network_device_overload` | Inspect CPU consumers and traffic spike/control-plane activity |
| Loss + low CPU + errors/interface down | `link_failure` | Compare both link ends, errors, optics/cable/neighbor state |
| Utilization >= 90% + loss/drops/latency | `network_congestion` | Identify top flows and alternate-path capacity |
| Memory >= 90% or little free memory | `memory_exhaustion` | Check memory trend, sessions, and process-level use |
| Unhealthy/unreachable node | `node_or_interface_failure` | Confirm power, peer state, and redundant path |
| Recent route/config change + loss/latency | `routing_or_configuration_issue` | Compare current state to the last known-good route/policy |

Hypotheses carry evidence, contradictions, confidence, and read-only next checks. They are never execution approvals.

## Recovery planning

The planner creates 2-5 declarative plans per diagnosis. Every plan contains preconditions, actions, verification, stop conditions, rollback, risk, and human-approval status.

| Failure | Typical plans |
|---|---|
| Device overload | bounded traffic shift, bulk throttling, abnormal-traffic containment, controlled failover/restart |
| Link failure | reroute, disable confirmed bad link, repair/replace |
| Congestion | bounded traffic shift, QoS, throttle bulk traffic, capacity upgrade |
| Memory exhaustion | limit non-critical sessions, failover/restart, patch or scale memory |
| Node/interface failure | fail over, controlled recovery, replace component |
| Routing/configuration issue | restore known-good config, narrow route correction, temporary traffic steering |

## Ranking recovery candidates

Plans are rejected before ranking if the Digital Twin fails, Safety Engine policy fails, rollback is absent, or backup resource use exceeds 90%.

Eligible plans receive a 0-100 score:

`0.30*downtime + 0.25*risk + 0.20*speed + 0.15*complexity + 0.10*resource_utilization`

Lower downtime, faster recovery, lower risk, lower complexity, and lower additional resource use score higher. The pipeline uses explicitly labelled fallback estimates only for the demo; Digital Twin estimates should replace them before any real decision.

## Human-readable summaries and LLM usage

`network_summary_generator.py` creates deterministic English summaries from diagnosis evidence. An LLM may rewrite the grounded output for a beginner, operator, or executive audience, but it must not introduce a new cause, metric, action, or confidence claim.

Recommended LLM rule: "Use only supplied grounded data. Clearly distinguish observed evidence from a likely hypothesis. Do not say a plan is approved or safe to execute."

## Running the prototype

See `README.md` for commands. `test_aegis_pipeline.py` exercises the sample overload incident end to end.
