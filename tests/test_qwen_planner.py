"""Unit tests for QwenRecoveryPlanner in backend/ai/qwen_planner.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.ai.qwen_planner import NemotronRecoveryPlanner, QwenRecoveryPlanner
from backend.models.enums import NodeStatus
from backend.models.recovery import RecoveryPlan
from backend.models.validation import parse_plan
from backend.telemetry import TelemetryEngine
from backend.diagnosis import HeuristicDiagnoser
from tests import fixtures


def _get_incident_state_and_dx():
    state = fixtures.network_state()
    # Mark N2 as failed
    state.nodes["N2"].status = NodeStatus.failed
    tel = TelemetryEngine().derive(state)
    dx = HeuristicDiagnoser().diagnose(state, [], tel)
    return state, dx


def test_qwen_planner_disabled_uses_fallback():
    state, dx = _get_incident_state_and_dx()
    planner = QwenRecoveryPlanner(enabled=False)
    plans = planner.plan(state, dx)
    assert len(plans) >= 1
    assert all(p.source == "heuristic" for p in plans)


def test_qwen_planner_unreachable_ollama_falls_back():
    state, dx = _get_incident_state_and_dx()
    planner = QwenRecoveryPlanner(
        enabled=True,
        ollama_url="http://localhost:11434",
        timeout=0.1,
    )

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
        plans = planner.plan(state, dx)

    assert len(plans) >= 1
    assert all(p.source == "heuristic" for p in plans)


def test_qwen_planner_successful_response():
    state, dx = _get_incident_state_and_dx()
    planner = QwenRecoveryPlanner(enabled=True)

    mock_ollama_resp = {
        "response": json.dumps({
            "plans": [
                {
                    "strategy_label": "Migrate services and isolate N2",
                    "rationale": "Relocate svc-auth to healthy node N1 then quarantine N2",
                    "actions": [
                        {"type": "migrate_service", "service_id": "svc-auth", "to_node": "N1"},
                        {"type": "quarantine_node", "node_id": "N2"},
                    ],
                }
            ]
        })
    }

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = mock_ollama_resp
    mock_http_response.raise_for_status.return_value = None

    with patch("httpx.Client.post", return_value=mock_http_response):
        plans = planner.plan(state, dx)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.source == "llm"
    assert plan.strategy_label == "Migrate services and isolate N2"
    assert len(plan.actions) == 2
    assert plan.actions[0].type == "migrate_service"
    assert plan.actions[1].type == "quarantine_node"
    # Verify it survives canonical schema validation
    parse_plan(plan.model_dump(mode="json"), state)


def test_qwen_planner_malformed_json_falls_back():
    state, dx = _get_incident_state_and_dx()
    planner = QwenRecoveryPlanner(enabled=True)

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = {"response": "Sorry, I cannot help with that."}
    mock_http_response.raise_for_status.return_value = None

    with patch("httpx.Client.post", return_value=mock_http_response):
        plans = planner.plan(state, dx)

    assert len(plans) >= 1
    assert all(p.source == "heuristic" for p in plans)


def test_qwen_planner_hallucinated_node_falls_back():
    state, dx = _get_incident_state_and_dx()
    planner = QwenRecoveryPlanner(enabled=True)

    mock_ollama_resp = {
        "response": json.dumps({
            "plans": [
                {
                    "strategy_label": "Isolate fake node",
                    "rationale": "Quarantine unknown node N999",
                    "actions": [
                        {"type": "quarantine_node", "node_id": "N999"}
                    ],
                }
            ]
        })
    }

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = mock_ollama_resp
    mock_http_response.raise_for_status.return_value = None

    with patch("httpx.Client.post", return_value=mock_http_response):
        plans = planner.plan(state, dx)

    # Referential integrity rejects N999 -> falls back to heuristic
    assert len(plans) >= 1
    assert all(p.source == "heuristic" for p in plans)


def test_nemotron_planner_nvidia_api_success():
    state, dx = _get_incident_state_and_dx()
    planner = NemotronRecoveryPlanner(
        enabled=True,
        nvidia_api_key="mock-nvapi-key",
    )

    mock_nvidia_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "plans": [
                            {
                                "strategy_label": "Nemotron Intelligent Isolation",
                                "rationale": "Migrate auth service to N1 then quarantine failed node N2",
                                "actions": [
                                    {"type": "migrate_service", "service_id": "svc-auth", "to_node": "N1"},
                                    {"type": "quarantine_node", "node_id": "N2"},
                                ],
                            }
                        ]
                    })
                }
            }
        ]
    }

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = mock_nvidia_resp
    mock_http_response.raise_for_status.return_value = None

    with patch("httpx.Client.post", return_value=mock_http_response):
        plans = planner.plan(state, dx)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.source == "llm"
    assert "Nemotron" in plan.strategy_label
    assert len(plan.actions) == 2
    assert plan.actions[0].type == "migrate_service"
    assert plan.actions[1].type == "quarantine_node"


def test_nemotron_planner_nvidia_api_error_falls_back():
    state, dx = _get_incident_state_and_dx()
    planner = NemotronRecoveryPlanner(
        enabled=True,
        nvidia_api_key="mock-nvapi-key",
        timeout=0.1,
    )

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("NVIDIA API connection error")):
        plans = planner.plan(state, dx)

    assert len(plans) >= 1
    assert all(p.source == "heuristic" for p in plans)

