# Aegis - AI Diagnosis + Recovery Planner

This folder contains the complete hackathon prototype for the Aegis diagnosis pipeline.

## Files

- `sample_telemetry.json` - simulator input example.
- `telemetry_schema.json` - JSON Schema contract for simulator payloads.
- `AI_DIAGNOSIS_GUIDE.md` - architecture, metrics, thresholds, diagnosis, planning, ranking, and LLM guardrails.
- `anomaly_detector.py` - detects measurable abnormal conditions.
- `diagnosis_engine.py` - turns correlated telemetry and events into ranked root-cause hypotheses.
- `recovery_planner.py` - generates 2-5 safe candidate plans per diagnosis.
- `recovery_plan_ranker.py` - filters unsafe plans and scores remaining candidates.
- `network_summary_generator.py` - produces human-readable incident summaries.
- `LLM_PLAN_EXPLANATION_PROMPT.md` - grounded prompt template for plan explanations.
- `network_failure_scenarios.py` - 20 telemetry fixtures plus generated expected/actual output artifacts.
- `test_network_failure_scenarios.py` - regression tests covering all 20 scenarios.
- `aegis_pipeline.py` - end-to-end entry point.
- `test_aegis_pipeline.py` - integration tests.

## Run the complete demo

From this folder, run:

```powershell
& "C:\Users\yyash\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .\aegis_pipeline.py
```

## Run tests

```powershell
& "C:\Users\yyash\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest .\test_aegis_pipeline.py
```

## Generate the 20-scenario JSON artifact

```powershell
& "C:\Users\yyash\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .\network_failure_scenarios.py
```

The command writes the complete JSON artifact to standard output. It includes each telemetry input, expected assertions, actual anomalies, diagnosis, recovery plans, ranking, and final Digital Twin handoff JSON.

## Simulator integration contract

1. The simulator posts a payload matching `telemetry_schema.json`.
2. Send it to `run_pipeline(payload)`.
3. The pipeline returns anomalies, diagnoses, candidate plans, rankings, and a human-readable summary.
4. Send each candidate to the Digital Twin. Return its estimates keyed by `plan_id` and call `run_pipeline(payload, simulation_estimates=...)` again.
5. Send only a Digital Twin-passed, Safety Engine-approved plan to an executor.

## Safety boundary

The Python code never sends commands to network devices. It emits declarative action intents such as `shift_traffic` or `restore_config_version`. A trusted executor, Digital Twin, and Safety Engine must validate and authorize any real action.
