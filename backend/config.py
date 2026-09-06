"""Central tunables — the only place hackathon knobs live (docs/TRD.md R5).

Threshold values here are SCAFFOLD DEFAULTS pending team agreement
(BACKEND_SCHEMA.md §10 / IMPLEMENTATION_PLAN.md TEAM DECISION D2, D5, D6).
"""

from __future__ import annotations

from backend.models.safety import PolicyConfig

# --- recovery / LLM ---------------------------------------------------------

LLM_ENABLED = False                      # D5 — demo runs on the deterministic fallback
LLM_MODEL = "claude-sonnet-4-5"          # placeholder; ai/ (Yyash) owns the real choice
RECOVERY_RUN_AUTO_APPLY_DEFAULT = True   # D6

# --- safety policy (D2 — values are TEAM DECISION REQUIRED) --------------

DEFAULT_POLICY = PolicyConfig(
    policy_version="p0-scaffold",
    availability_floor=0.99,
    max_latency_increase_ratio=0.20,
    max_node_load_ratio=0.90,
    warnings_block=False,
)
