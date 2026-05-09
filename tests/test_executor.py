"""Tests for InputExecutor: TAP, WAIT, HOLD, no fake keys, and sequence correctness."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import time

from vcl_input.executor import InputExecutor, ActionSequence, DeferredAction, DeferredActionType
from vcl_input.primitives import InputPrimitives
from vcl_core.schemas import Wave1ActionName
from vcl_core.config import AppConfig, KeybindsConfig


def _make_fake_primitives():
    """InputPrimitives that record press/release calls without real keyboard."""

    class FakePrimitives(InputPrimitives):
        def __init__(self):
            super().__init__(keybinds=KeybindsConfig())
            self._presses: list[str] = []
            self._releases: list[str] = []

        def _default_press(self, key: str) -> None:
            self._presses.append(key)

        def _default_release(self, key: str) -> None:
            self._releases.append(key)

        def clear(self) -> None:
            self._presses.clear()
            self._releases.clear()

    return FakePrimitives()


class TestTAPAction:
    """TAP must press, wait, release."""

    def test_tap_presses_key(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="tap_test",
            steps=[DeferredAction(DeferredActionType.TAP, "space", 80)],
        )
        seq.start(time.monotonic())
        # First tick: press
        seq.tick(p, time.monotonic())
        assert "space" in p._presses, "TAP should press key on first tick"

    def test_tap_releases_key(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="tap_test",
            steps=[DeferredAction(DeferredActionType.TAP, "space", 80)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now)  # press
        # Wait past down_ms
        seq.tick(p, now + 0.1)  # release + advance
        assert "space" in p._releases, "TAP should release key after down_ms elapsed"

    def test_tap_presses_and_releases_exactly_once(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="tap_test",
            steps=[DeferredAction(DeferredActionType.TAP, "r", 80)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now)  # press
        seq.tick(p, now + 0.1)  # release
        assert p._presses.count("r") == 1, "TAP should press exactly once"
        assert p._releases.count("r") == 1, "TAP should release exactly once"

    def test_tap_press_before_wait_elapsed(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="tap_test",
            steps=[DeferredAction(DeferredActionType.TAP, "space", 200)],
        )
        now = time.monotonic()
        seq.start(now)
        result1 = seq.tick(p, now)  # press
        result2 = seq.tick(p, now + 0.05)  # still within down_ms
        assert p._presses.count("space") == 1, "Should not re-press during wait"
        assert result2 == "running", "TAP should still be running before down_ms"


class TestWAITAction:
    """WAIT must never call press or release."""

    def test_wait_does_not_press(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="wait_test",
            steps=[DeferredAction(DeferredActionType.WAIT, down_ms=500)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now)
        seq.tick(p, now + 0.3)
        assert len(p._presses) == 0, "WAIT should never press any key"

    def test_wait_does_not_release(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="wait_test",
            steps=[DeferredAction(DeferredActionType.WAIT, down_ms=500)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now + 0.4)
        seq.tick(p, now + 0.6)
        assert len(p._releases) == 0, "WAIT should never release any key"

    def test_wait_advances_after_duration(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="wait_test",
            steps=[DeferredAction(DeferredActionType.WAIT, down_ms=100)],
        )
        now = time.monotonic()
        seq.start(now)
        result1 = seq.tick(p, now)
        assert result1 == "running"
        result2 = seq.tick(p, now + 0.2)
        assert result2 == "done"


class TestHOLDAction:
    """HOLD must press and wait full duration before releasing."""

    def test_hold_presses_key(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="hold_test",
            steps=[DeferredAction(DeferredActionType.HOLD, "r", 500)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now)
        assert "r" in p._presses, "HOLD should press key"

    def test_hold_releases_after_duration(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="hold_test",
            steps=[DeferredAction(DeferredActionType.HOLD, "r", 200)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now)  # press
        seq.tick(p, now + 0.1)  # still waiting
        result = seq.tick(p, now + 0.3)  # duration elapsed
        assert "r" in p._releases, "HOLD should release after down_ms"
        assert result == "done"

    def test_hold_does_not_release_before_duration(self):
        p = _make_fake_primitives()
        seq = ActionSequence(
            name="hold_test",
            steps=[DeferredAction(DeferredActionType.HOLD, "w", 200)],
        )
        now = time.monotonic()
        seq.start(now)
        seq.tick(p, now)  # press
        seq.tick(p, now + 0.1)  # still within duration
        assert "w" not in p._releases, "HOLD should not release before duration"


class TestSequencePatterns:
    """Real-world sequence patterns must not use fake keys."""

    def test_geppo_never_presses_dummy_wait(self):
        """Geppo sequence must never contain dummy_wait."""
        cfg = AppConfig()
        p = _make_fake_primitives()
        executor = InputExecutor(config=cfg, primitives=p)
        seq = executor._build_geppo_seq()
        keys_used = [s.key for s in seq.steps if s.key is not None]
        assert "dummy_wait" not in keys_used, "Geppo must not use dummy_wait"
        assert "infinite_wait" not in keys_used, "Geppo must not use infinite_wait"
        # Should have real keys
        assert "space" in keys_used, "Geppo should use jump key"
        assert "s" in keys_used, "Geppo should use backward key"

    def test_geppo_uses_wait_for_intervals(self):
        """Geppo interval waits must be WAIT type, not fake HOLD."""
        cfg = AppConfig()
        p = _make_fake_primitives()
        executor = InputExecutor(config=cfg, primitives=p)
        seq = executor._build_geppo_seq()
        wait_steps = [s for s in seq.steps if s.action_type == DeferredActionType.WAIT]
        hold_steps = [s for s in seq.steps if s.action_type == DeferredActionType.HOLD]
        assert len(wait_steps) > 0, "Geppo should have WAIT steps for intervals"
        # Only one HOLD for backward key
        assert len(hold_steps) == 1, "Geppo should have exactly one HOLD (backward)"
        assert hold_steps[0].key == "s", "Geppo HOLD should be backward key"

    def test_observation_scan_never_presses_dummy_wait(self):
        cfg = AppConfig()
        p = _make_fake_primitives()
        executor = InputExecutor(config=cfg, primitives=p)
        seq = executor._build_observation_scan_seq()
        keys_used = [s.key for s in seq.steps if s.key is not None]
        assert "dummy_wait" not in keys_used, "Observation scan must not use dummy_wait"
        assert "infinite_wait" not in keys_used, "Observation scan must not use infinite_wait"
        assert "g" in keys_used, "Observation scan should use G key"

    def test_observation_scan_uses_wait_type(self):
        cfg = AppConfig()
        executor = InputExecutor(config=AppConfig())
        seq = executor._build_observation_scan_seq()
        wait_steps = [s for s in seq.steps if s.action_type == DeferredActionType.WAIT]
        hold_steps = [s for s in seq.steps if s.action_type == DeferredActionType.HOLD]
        assert len(wait_steps) == 1, "Observation scan should have exactly one WAIT"
        assert len(hold_steps) == 0, "Observation scan should have zero HOLD steps"
        assert wait_steps[0].key is None, "WAIT steps have no key"

    def test_move_to_exit_never_presses_infinite_wait(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        seq = executor._build_move_to_exit_seq()
        keys_used = [s.key for s in seq.steps if s.key is not None]
        assert "infinite_wait" not in keys_used, "Move to exit must not use infinite_wait"
        assert "dummy_wait" not in keys_used, "Move to exit must not use dummy_wait"
        assert "w" in keys_used, "Move to exit should use forward key"

    def test_move_to_exit_releases_forward_key(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        seq = executor._build_move_to_exit_seq()
        release_steps = [s for s in seq.steps if s.action_type == DeferredActionType.RELEASE]
        assert len(release_steps) == 1, "Move to exit should release the forward key"
        assert release_steps[0].key == "w", "Move to exit RELEASE should be forward key"

    def test_move_to_enemy_never_presses_infinite_wait(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        seq = executor._build_move_to_enemy_seq()
        keys_used = [s.key for s in seq.steps if s.key is not None]
        assert "infinite_wait" not in keys_used, "Move to enemy must not use infinite_wait"
        assert "dummy_wait" not in keys_used, "Move to enemy must not use dummy_wait"


class TestExecutorIntegration:
    """Executor end-to-end with fake primitives."""

    def test_executor_press_slot_2_emits_tap(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        executor.execute(Wave1ActionName.PRESS_SLOT_2)
        assert len(executor._queue) == 1
        seq = executor._queue[0]
        assert seq.name == "press_slot_2"
        assert len(seq.steps) == 1
        assert seq.steps[0].action_type == DeferredActionType.TAP
        assert seq.steps[0].key == "2"

    def test_executor_geppo_emits_geppo_sequence(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        executor.execute(Wave1ActionName.GEPPO_STACK)
        assert len(executor._queue) == 1
        seq = executor._queue[0]
        assert seq.name == "geppo"

    def test_executor_hold_radiant_kick_emits_hold_and_release(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        executor.execute(Wave1ActionName.HOLD_RADIANT_KICK)
        seq = executor._queue[0]
        types = [s.action_type for s in seq.steps]
        assert DeferredActionType.HOLD in types
        assert DeferredActionType.RELEASE in types

    def test_executor_is_idle_when_empty(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        assert executor.is_idle is True

    def test_executor_is_not_idle_after_execute(self):
        cfg = AppConfig()
        executor = InputExecutor(config=cfg)
        executor.execute(Wave1ActionName.PRESS_SLOT_2)
        assert executor.is_idle is False

    def test_executor_idle_after_tick_completes(self):
        cfg = AppConfig()
        p = _make_fake_primitives()
        executor = InputExecutor(config=cfg, primitives=p)
        executor.execute(Wave1ActionName.PRESS_SLOT_2)
        assert executor.is_idle is False
        # execute() queues the sequence; first tick() pops it into _current
        executor.tick()
        assert executor._current is not None
        # Advance time past TAP down_ms (80ms)
        executor._current._subaction_start = time.monotonic() - 1.0
        for _ in range(5):
            executor.tick()
        assert executor.is_idle is True
