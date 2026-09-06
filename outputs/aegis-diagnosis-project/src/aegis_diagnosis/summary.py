"""Grounded operator-facing incident summaries."""

from .models import Hypothesis


class SummaryGenerator:
    def generate(self, telemetry: dict, top: Hypothesis | None) -> dict:
        incident = telemetry["incident"]
        if not top:
            return {"headline": f"{incident['incident_id']}: Insufficient evidence", "status": "warning", "executive_summary": "No root-cause hypothesis could be formed from supplied telemetry."}
        evidence = "; ".join(top.supporting_evidence[:3])
        return {"headline": f"{incident['incident_id']}: {top.root_cause.replace('_', ' ').title()}", "status": "critical" if top.confidence == "high" else "warning", "executive_summary": f"{top.explanation} Evidence: {evidence}", "affected_services": incident.get("affected_services", [])}
