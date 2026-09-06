"""Execution boundary — applies ONLY safety-approved recovery plans, via
StateManager. Never mutates NetworkState directly, never calls AI, never
bypasses safety approval (architecture invariants 5, 10).
"""

from __future__ import annotations

from backend.execution.executor import ExecutionResult, Executor

__all__ = ["Executor", "ExecutionResult"]
