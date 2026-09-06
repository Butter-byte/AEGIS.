# Aegis Diagnosis Project

## Structure

```text
src/aegis_diagnosis/
  validation.py  - untrusted telemetry boundary
  anomaly.py     - deterministic threshold rules
  diagnosis.py   - correlated root-cause hypotheses
  summary.py     - grounded English summary
  planning.py    - constrained recovery-plan catalog
  ranking.py     - safety-gated scoring
  pipeline.py    - public orchestration entry point
  models.py      - shared typed domain objects
tests/           - pipeline tests
```

## Run tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover tests -v
```

## Use

```python
from aegis_diagnosis import AegisPipeline

result = AegisPipeline().run(telemetry_payload)
```

`result` is the final Diagnosis-to-Digital-Twin handoff JSON. The package never executes network commands; it produces candidate plans only.
