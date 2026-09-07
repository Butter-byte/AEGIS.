"""Central tunables — the only place hackathon knobs live (docs/TRD.md R5).

Threshold values here are SCAFFOLD DEFAULTS pending team agreement
(BACKEND_SCHEMA.md §10 / IMPLEMENTATION_PLAN.md TEAM DECISION D2, D5, D6).
"""

import os

from backend.models.safety import PolicyConfig

# --- recovery / LLM ---------------------------------------------------------

LLM_ENABLED = os.getenv("AEGIS_LLM_ENABLED", "false").lower() in ("true", "1", "yes")
LLM_MODEL = os.getenv("AEGIS_LLM_MODEL", "qwen2.5:3b")
OLLAMA_URL = os.getenv("AEGIS_OLLAMA_URL", "http://localhost:11434")
RECOVERY_RUN_AUTO_APPLY_DEFAULT = True   # D6

# --- safety policy (D2 — values are TEAM DECISION REQUIRED) --------------

DEFAULT_POLICY = PolicyConfig(
    policy_version="p0-scaffold",
    availability_floor=0.99,
    max_latency_increase_ratio=0.20,
    max_node_load_ratio=0.90,
    warnings_block=False,
)
