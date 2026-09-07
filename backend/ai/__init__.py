"""backend/ai/ — AI Diagnosis & Recovery Planning (Yyash).

Provides LLM-backed recovery planning with deterministic fallback.
Advisory / data-only: imports no execution, state mutators, or safety engines.
"""

from .qwen_planner import NemotronRecoveryPlanner, QwenRecoveryPlanner

__all__ = ["NemotronRecoveryPlanner", "QwenRecoveryPlanner"]
