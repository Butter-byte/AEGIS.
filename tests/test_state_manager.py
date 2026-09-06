"""StateManager — the single authoritative mutation boundary."""

from __future__ import annotations

import pytest

from backend.state.manager import StateInvariantError, StateManager
from backend.state.mutations import set_node
from backend.state.seed import build_seed


@pytest.fixture
def sm() -> StateManager:
    return StateManager(build_seed())


def test_get_state_returns_deep_copy(sm):
    a = sm.get_state()
    a.nodes["N1"].cpu_percent = 999.0
    assert sm.get_state().nodes["N1"].cpu_percent != 999.0


def test_apply_actions_bumps_version_by_one(sm):
    assert sm.current_version() == 0
    sm.apply_actions([set_node("N1", cpu_percent=55.0)], reason="test")
    assert sm.current_version() == 1
    assert sm.get_state().nodes["N1"].cpu_percent == 55.0


def test_invalid_mutation_leaves_state_untouched(sm):
    before = sm.get_state()
    with pytest.raises(StateInvariantError):
        sm.apply_actions([set_node("N1", cpu_percent=500.0)], reason="bad")
    assert sm.get_state() == before
    assert sm.current_version() == 0


def test_unknown_target_rejected(sm):
    with pytest.raises(StateInvariantError):
        sm.apply_actions([set_node("N999", cpu_percent=1.0)], reason="bad")


def test_empty_batch_rejected(sm):
    with pytest.raises(StateInvariantError):
        sm.apply_actions([], reason="bad")


def test_reset_is_a_forward_mutation(sm):
    sm.apply_actions([set_node("N1", cpu_percent=55.0)], reason="test")
    assert sm.current_version() == 1
    sm.reset(build_seed())
    assert sm.current_version() == 2  # never resets to 0
    assert sm.get_state().nodes["N1"].cpu_percent == 20.0


def test_subscribers_notified_with_snapshot(sm):
    seen = []
    sm.subscribe(lambda s: seen.append(s.version))
    sm.apply_actions([set_node("N1", cpu_percent=30.0)], reason="test")
    assert seen == [1]


def test_broken_subscriber_does_not_undo_commit(sm):
    sm.subscribe(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    sm.apply_actions([set_node("N1", cpu_percent=30.0)], reason="test")
    assert sm.current_version() == 1
