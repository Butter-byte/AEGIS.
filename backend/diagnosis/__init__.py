"""backend/diagnosis/ — Yyash. Deterministic AI diagnosis -> one canonical Diagnosis.

Contract: docs/BACKEND_SCHEMA.md §4. Port: the `Diagnoser` Protocol in
backend/pipeline.py. Advisory / data-only — never mutates network state.
"""

from .heuristic import HeuristicDiagnoser

__all__ = ["HeuristicDiagnoser"]
