"""Local LLM Recovery Planner using Qwen (via Ollama) with deterministic fallback.

Owner: Yyash (AI Diagnosis + Recovery Planner).
Boundary: Advisory / data-only. Does not import state, execution, twin, or safety.
Schema: Closed 6-action vocabulary only (invariant 4/13). Validated by parse_plan().
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from backend.config import LLM_ENABLED, LLM_MODEL, OLLAMA_URL
from backend.models.common import new_plan_id, utcnow
from backend.models.diagnosis import Diagnosis
from backend.models.enums import NodeStatus
from backend.models.recovery import RecoveryPlan
from backend.models.state import NetworkState
from backend.models.validation import SchemaError, parse_plan
from backend.recovery.planner import RecoveryPlanner

logger = logging.getLogger(__name__)

_CLOSED_VOCAB = {
    "reroute", "drain_node", "restore_node", "migrate_service", "quarantine_node", "reset_link",
}
_MAX_ACTIONS = 6


class QwenRecoveryPlanner:
    """Ollama/Qwen-powered recovery planner with seamless heuristic fallback.

    Implements the `Planner` protocol required by `backend.pipeline.Pipeline`.
    """

    def __init__(
        self,
        fallback_planner: RecoveryPlanner | None = None,
        *,
        model: str | None = None,
        ollama_url: str | None = None,
        timeout: float = 4.0,
        enabled: bool | None = None,
    ) -> None:
        self.fallback = fallback_planner or RecoveryPlanner()
        self.model = model or LLM_MODEL
        self.ollama_url = (ollama_url or OLLAMA_URL).rstrip("/")
        self.timeout = timeout
        self.enabled = LLM_ENABLED if enabled is None else enabled

    def plan(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        """Generate candidate recovery plans, attempting Qwen first if enabled."""
        if not self.enabled:
            return self.fallback.plan(state, diagnosis)

        # If nothing is suspected, let fallback handle (returns empty list)
        if not diagnosis.suspected_nodes and not diagnosis.suspected_edges:
            return self.fallback.plan(state, diagnosis)

        try:
            candidate_plans = self._query_qwen(state, diagnosis)
            if candidate_plans:
                return candidate_plans
        except Exception as exc:
            logger.warning("Qwen planning failed or returned invalid output; falling back: %s", exc)

        return self.fallback.plan(state, diagnosis)

    # --- internal LLM orchestration ------------------------------------------

    def _query_qwen(self, state: NetworkState, diagnosis: Diagnosis) -> list[RecoveryPlan]:
        prompt = self._build_prompt(state, diagnosis)
        endpoint = f"{self.ollama_url}/api/generate"

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 2048,
            },
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()

        raw_response = data.get("response", "{}")
        parsed = json.loads(raw_response)

        raw_plans = parsed.get("plans") if isinstance(parsed, dict) else None
        if not isinstance(raw_plans, list) or not raw_plans:
            # Check if model returned a single plan directly
            if isinstance(parsed, dict) and "actions" in parsed:
                raw_plans = [parsed]
            else:
                return []

        validated_plans: list[RecoveryPlan] = []
        for p in raw_plans:
            if not isinstance(p, dict):
                continue

            actions = p.get("actions", [])
            if not isinstance(actions, list) or not actions:
                continue

            # Ensure actions contain at least one effective action
            trimmed_actions = actions[:_MAX_ACTIONS]

            candidate_dict = {
                "id": new_plan_id(),
                "created_at": utcnow().isoformat(),
                "based_on_version": state.version,
                "targets_diagnosis": diagnosis.id,
                "strategy_label": str(p.get("strategy_label", "AI Generated Plan"))[:120],
                "rationale": str(p.get("rationale", "Plan proposed by Qwen"))[:2000],
                "actions": trimmed_actions,
                "source": "llm",
            }

            try:
                # Strictly validate through AEGIS schema validator
                validated = parse_plan(candidate_dict, state)
                validated_plans.append(validated)
            except (SchemaError, Exception) as val_exc:
                logger.debug("Discarding invalid LLM plan candidate: %s", val_exc)
                continue

        return validated_plans

    def _build_prompt(self, state: NetworkState, diagnosis: Diagnosis) -> str:
        healthy_nodes = [
            n.id for n in state.nodes.values()
            if n.status == NodeStatus.healthy and n.id not in diagnosis.suspected_nodes
        ]

        impacted_services = [
            {"id": s.id, "host_node": s.host_node}
            for s in state.services.values()
            if s.id in diagnosis.suspected_services or s.host_node in diagnosis.suspected_nodes
        ]

        incident_context = {
            "diagnosis_summary": diagnosis.summary,
            "suspected_nodes": diagnosis.suspected_nodes,
            "suspected_edges": diagnosis.suspected_edges,
            "impacted_services": impacted_services,
            "healthy_target_nodes": healthy_nodes,
        }

        return f"""You are the AEGIS Autonomous Network Recovery Planner.
A network incident has occurred and requires safe remediation candidate plans.

INCIDENT CONTEXT:
{json.dumps(incident_context, indent=2)}

CLOSED ACTION VOCABULARY (You may ONLY use these actions):
1. migrate_service: {{"type": "migrate_service", "service_id": "<id>", "to_node": "<healthy_node>"}}
2. quarantine_node: {{"type": "quarantine_node", "node_id": "<node_id>"}}
3. drain_node: {{"type": "drain_node", "node_id": "<node_id>"}}
4. restore_node: {{"type": "restore_node", "node_id": "<node_id>"}}
5. reset_link: {{"type": "reset_link", "edge_id": "<edge_id>"}}
6. reroute: {{"type": "reroute", "service_id": "<id>", "avoid_nodes": [...], "avoid_edges": [...]}}

RULES:
- Propose 1 to 3 distinct candidate plans.
- Only reference valid node IDs, service IDs, and edge IDs listed in the INCIDENT CONTEXT.
- If a service host node is failing, ALWAYS migrate its service to a healthy node before or when isolating.
- Every plan must contain at least one effective action (migrate_service, quarantine_node, reset_link, or restore_node).
- Output STRICTLY valid JSON with no markdown formatting, backticks, or extra explanation.

JSON OUTPUT FORMAT:
{{
  "plans": [
    {{
      "strategy_label": "Short descriptive label (max 120 chars)",
      "rationale": "Reasoning for the candidate plan (max 2000 chars)",
      "actions": [
        {{"type": "migrate_service", "service_id": "svc-auth", "to_node": "N1"}},
        {{"type": "quarantine_node", "node_id": "N7"}}
      ]
    }}
  ]
}}"""
