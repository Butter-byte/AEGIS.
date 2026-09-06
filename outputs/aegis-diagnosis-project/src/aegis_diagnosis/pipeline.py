"""Orchestration layer; the only public entry point required by an API/UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .anomaly import AnomalyDetector
from .diagnosis import DiagnosisEngine
from .models import to_json
from .planning import RecoveryPlanner
from .ranking import PlanRanker, WEIGHTS
from .summary import SummaryGenerator
from .validation import validate_telemetry


class AegisPipeline:
    def __init__(self) -> None:
        self.detector = AnomalyDetector(); self.diagnoser = DiagnosisEngine(); self.summarizer = SummaryGenerator(); self.planner = RecoveryPlanner(); self.ranker = PlanRanker()

    def run(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        errors = validate_telemetry(telemetry)
        if errors: return {"status": "invalid_input", "validation_errors": errors}
        findings = self.detector.detect(telemetry); hypotheses = self.diagnoser.diagnose(telemetry, findings); top = hypotheses[0] if hypotheses else None
        all_plans = [plan for hypothesis in hypotheses[:3] for plan in self.planner.generate(hypothesis)]
        ranked = self.ranker.rank(all_plans); generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "schema_version": "1.0", "status": "ok", "output_id": f"diagnosis-{telemetry['incident']['incident_id']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}", "generated_at": generated_at,
            "incident": telemetry["incident"], "network_summary": self.summarizer.generate(telemetry, top),
            "anomalies": to_json(findings), "diagnosis": {"most_likely_root_cause": to_json(top) if top else None, "hypotheses": to_json(hypotheses)},
            "recovery_plans": to_json(all_plans), "ranking": {"algorithm_version": "1.0", "weights": WEIGHTS, "ranked_plans": to_json(ranked)},
            "digital_twin_handoff": {"status": "pending_simulation", "plans_to_simulate": [item.plan_id for item in ranked if item.eligible], "execution_rule": "No plan may execute until Digital Twin validation and bounded Safety Engine approval succeed."},
        }
