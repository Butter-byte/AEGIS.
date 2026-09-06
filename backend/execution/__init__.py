"""Execution boundary (Vikash) — applies ONLY safety-approved plans, via
StateManager. Never mutates NetworkState directly, never calls a planner or the
safety gate, never bypasses approval.

Import from `backend.execution.executor` / `backend.execution.translate` directly.
"""
