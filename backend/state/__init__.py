"""Authoritative live-state ownership (Vikash).

StateManager is the only writer of the live NetworkState; mutations enter through
`apply_actions()` only, as mechanical primitives. Import from the submodules
directly: `backend.state.manager`, `backend.state.mutations`,
`backend.state.preview`, `backend.state.seed`.
"""
