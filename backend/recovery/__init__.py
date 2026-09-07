"""backend/recovery/ — Yyash. Diagnosis -> candidate RecoveryPlans.

Closed 6-action vocabulary only (invariant 4/13). Contract: docs/BACKEND_SCHEMA.md
§5. Port: the `Planner` Protocol in backend/pipeline.py. Advisory / data-only —
the pipeline simulates + safety-gates before the Executor applies anything.
"""

from .planner import RecoveryPlanner

__all__ = ["RecoveryPlanner"]
