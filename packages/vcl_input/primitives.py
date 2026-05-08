"""Input primitives for Wave 1 combat actions."""
from __future__ import annotations

import time
import random
from typing import Callable

from vcl_core.config import KeybindsConfig


class InputPrimitives:
    """
    Low-level input primitives for Wave 1.

    All methods that interact with the OS keyboard go through here.
    Kept separate from executor logic for easy testing.
    """

    def __init__(
        self,
        keybinds: KeybindsConfig | None = None,
        press_fn: Callable[[str], None] | None = None,
        release_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.keybinds = keybinds or KeybindsConfig()
        self._held_keys: set[str] = set()
        self._stopped = False
        self._press_fn = press_fn or self._default_press
        self._release_fn = release_fn or self._default_release

    def _default_press(self, key: str) -> None:
        try:
            import pynput
            from pynput.keyboard import Controller, Key
            c = Controller()
            try:
                k = getattr(Key, key, None) or Key._value_(key)
            except Exception:
                k = key
            c.press(k)
        except Exception:
            pass

    def _default_release(self, key: str) -> None:
        try:
            import pynput
            from pynput.keyboard import Controller, Key
            c = Controller()
            try:
                k = getattr(Key, key, None) or Key._value_(key)
            except Exception:
                k = key
            c.release(k)
        except Exception:
            pass

    def tap(self, key: str, down_ms: int = 80) -> None:
        """Press and release a key."""
        if self._stopped:
            return
        self._press_fn(key)
        self._held_keys.add(key)
        time.sleep(down_ms / 1000.0)
        self._release_fn(key)
        self._held_keys.discard(key)

    def hold(self, key: str) -> None:
        """Hold a key down."""
        if self._stopped:
            return
        self._press_fn(key)
        self._held_keys.add(key)

    def release(self, key: str) -> None:
        """Release a held key."""
        self._release_fn(key)
        self._held_keys.discard(key)

    def release_all_keys(self) -> None:
        """Release all currently held keys. Called on emergency stop."""
        ALL_KEYS = [
            self.keybinds.forward, self.keybinds.backward,
            self.keybinds.jump, self.keybinds.radiant_kick,
            self.keybinds.dash, self.keybinds.blitz_strike,
            self.keybinds.observation_haki, self.keybinds.armament_haki,
            "a", "d", "q", "e", "r", "g", "j", "space", "w", "s",
        ]
        for key in ALL_KEYS:
            self._release_fn(key)
        self._held_keys.clear()
        self._stopped = True

    def resume(self) -> None:
        """Resume input after emergency stop."""
        self._stopped = False

    def press_slot_pika_v2(self) -> None:
        """Select Pika V2 slot."""
        self.tap(self.keybinds.slot_pika_v2, down_ms=80)

    def press_armament_haki(self) -> None:
        """Activate Armament Haki."""
        self.tap(self.keybinds.armament_haki, down_ms=80)

    def geppo_stack(
        self,
        count: int = 5,
        interval_ms_min: int = 100,
        interval_ms_max: int = 180,
    ) -> None:
        """
        Execute geppo stack: hold W+S and tap Space rapidly.

        This lifts the player to maintain aerial advantage before Radiant Kick.
        """
        if self._stopped:
            return

        self.hold(self.keybinds.forward)
        self.hold(self.keybinds.backward)

        for i in range(count):
            if self._stopped:
                break
            self.tap(self.keybinds.jump, down_ms=60)
            interval = random.uniform(interval_ms_min, interval_ms_max) / 1000.0
            time.sleep(interval)

        self.release(self.keybinds.backward)

    def charged_radiant_kick(self, charge_ms: int = 1900) -> None:
        """
        Execute Charged Radiant Kick: hold R for charge window, then release.

        The charge window is ~1900ms. After gold flash, 3 AoE bursts fire.
        Costs 45 stamina, 13s cooldown.
        """
        if self._stopped:
            return
        self.hold(self.keybinds.radiant_kick)
        time.sleep(charge_ms / 1000.0)
        if not self._stopped:
            self.release(self.keybinds.radiant_kick)

    def observation_scan(self, tap_ms: int = 80) -> None:
        """Tap G to activate Observation Haki for a brief scan."""
        if self._stopped:
            return
        self.tap(self.keybinds.observation_haki, down_ms=tap_ms)

    def cleanup_attack(self) -> None:
        """Fallback attack when Radiant Kick didn't clear all enemies."""
        if self._stopped:
            return
        self.tap(self.keybinds.forward, down_ms=100)
        self.tap("1", down_ms=200)
        self.tap(self.keybinds.blitz_strike, down_ms=200)

    def align_camera_left(self, steps: int = 5) -> None:
        """Move camera left to adjust compass heading."""
        if self._stopped:
            return
        for _ in range(steps):
            self.tap("a", down_ms=50)

    def align_camera_right(self, steps: int = 5) -> None:
        """Move camera right to adjust compass heading."""
        if self._stopped:
            return
        for _ in range(steps):
            self.tap("d", down_ms=50)

    def move_forward(self, duration_ms: int = 500) -> None:
        """Hold W to move forward."""
        if self._stopped:
            return
        self.hold(self.keybinds.forward)
        time.sleep(duration_ms / 1000.0)
        if not self._stopped:
            self.release(self.keybinds.forward)

    def dash_forward(self) -> None:
        """Tap Q to dash forward."""
        if self._stopped:
            return
        self.tap(self.keybinds.dash, down_ms=100)

    @property
    def held_keys(self) -> set[str]:
        return self._held_keys.copy()
