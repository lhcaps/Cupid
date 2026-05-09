"""Tests for InputPrimitives safety — shared instance, release_all_keys, low-confidence."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from vcl_input.primitives import InputPrimitives
from vcl_input.executor import InputExecutor
from vcl_input.emergency_stop import EmergencyStop
from vcl_core.config import KeybindsConfig, AppConfig


class TestInputSafety:
    def test_executor_and_estop_share_same_primitives_instance(self):
        """InputExecutor and EmergencyStop must share the same InputPrimitives."""
        cfg = AppConfig()
        primitives = InputPrimitives(keybinds=cfg.keybinds)
        executor = InputExecutor(config=cfg, primitives=primitives)
        estop = EmergencyStop(primitives=primitives)

        assert executor.primitives is primitives
        assert estop._primitives is primitives
        assert executor.primitives is estop._primitives

    def test_release_all_keys_releases_movement_and_skill_keys(self):
        """release_all_keys must release all movement and skill keys."""
        keys_released: list[str] = []

        class MockPrimitives(InputPrimitives):
            def _default_release(self, key: str) -> None:
                keys_released.append(key)

        p = MockPrimitives()
        p.hold("w")
        p.hold("space")
        p.hold("r")
        p.hold("e")
        p.hold("q")
        p.hold("j")
        p.hold("g")

        p.release_all_keys()

        assert "w" in keys_released
        assert "space" in keys_released
        assert "r" in keys_released
        assert "e" in keys_released
        assert "q" in keys_released
        assert "j" in keys_released
        assert "g" in keys_released

    def test_release_all_keys_clears_held_keys(self):
        """After release_all_keys, held_keys must be empty."""
        p = InputPrimitives()
        p.hold("w")
        p.hold("space")
        assert len(p.held_keys) == 2

        p.release_all_keys()
        assert len(p.held_keys) == 0

    def test_estop_releases_keys_held_by_executor(self):
        """EmergencyStop must release keys held by the shared executor primitives."""
        keys_released: list[str] = []

        class MockPrimitives(InputPrimitives):
            def _default_release(self, key: str) -> None:
                keys_released.append(key)

        primitives = MockPrimitives()
        executor = InputExecutor(primitives=primitives)
        estop = EmergencyStop(primitives=primitives)

        primitives.hold("w")
        primitives.hold("r")

        assert len(primitives.held_keys) == 2

        estop.trigger()

        assert "w" in keys_released
        assert "r" in keys_released
        assert len(primitives.held_keys) == 0

    def test_estop_is_idempotent(self):
        """Multiple estop triggers should not double-release or crash."""
        p = InputPrimitives()
        estop = EmergencyStop(primitives=p)

        p.hold("w")
        estop.trigger()
        first_stopped = estop.is_stopped

        estop.trigger()
        second_stopped = estop.is_stopped

        assert first_stopped is True
        assert second_stopped is True

    def test_executor_emergency_stop_releases_all(self):
        """InputExecutor.emergency_stop must release all keys."""
        keys_released: list[str] = []

        class MockPrimitives(InputPrimitives):
            def _default_release(self, key: str) -> None:
                keys_released.append(key)

        primitives = MockPrimitives()
        executor = InputExecutor(primitives=primitives)

        primitives.hold("w")
        primitives.hold("space")
        primitives.hold("r")

        executor.emergency_stop()

        assert "w" in keys_released
        assert "space" in keys_released
        assert "r" in keys_released
        assert len(primitives.held_keys) == 0

    def test_release_held_keys_does_not_set_stopped(self):
        """release_held_keys must NOT set _stopped=True (only release_all_keys does)."""
        p = InputPrimitives()
        p.hold("w")
        p.hold("space")
        assert not p._stopped

        p.release_held_keys()
        assert len(p.held_keys) == 0
        assert not p._stopped, "release_held_keys must not set _stopped=True"

    def test_release_all_keys_sets_stopped(self):
        """release_all_keys must set _stopped=True."""
        p = InputPrimitives()
        p.hold("r")
        p.release_all_keys()
        assert p._stopped

    def test_release_held_keys_allows_resume(self):
        """After release_held_keys, primitives can still hold keys (no hard stop)."""
        p = InputPrimitives()
        p.release_held_keys()
        p.hold("w")
        assert "w" in p.held_keys

    def test_release_held_keys_includes_slots_1_and_2(self):
        """release_held_keys must release slot keys '1' and '2' and slot_pika_v2."""
        keys_released: list[str] = []

        class MockPrimitives(InputPrimitives):
            def _default_release(self, key: str) -> None:
                keys_released.append(key)

        p = MockPrimitives()
        p.hold("w")
        p.hold("1")
        p.hold("2")
        p.hold(p.keybinds.slot_pika_v2)

        p.release_held_keys()

        assert "1" in keys_released, "release_held_keys must release '1'"
        assert "2" in keys_released, "release_held_keys must release '2'"
        assert p.keybinds.slot_pika_v2 in keys_released, \
            "release_held_keys must release configured slot_pika_v2"
        assert "w" in keys_released, "release_held_keys must still release 'w'"
