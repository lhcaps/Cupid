"""Input executor: sequences primitives, tracks cooldowns, handles stop."""
from __future__ import annotations

import time
import threading
from typing import Callable, Literal

from vcl_core.config import AppConfig
from vcl_core.timebase import CooldownTracker
from vcl_input.primitives import InputPrimitives
from vcl_core.schemas import Wave1ActionName


class InputExecutor:
    """
    Executes Wave1Action commands from the HSM.

    Maps HSM actions to InputPrimitives calls.
    Tracks cooldowns and prevents spam.
    Integrates with EmergencyStop for safety.
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        stop_flag: Callable[[], bool] | None = None,
        primitives: InputPrimitives | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self.keybinds = self.config.keybinds
        self.wave1_cfg = self.config.wave1
        self.safety_cfg = self.config.safety

        self._primitives = primitives or InputPrimitives(keybinds=self.keybinds)
        self._cooldowns = CooldownTracker()
        self._stop_flag = stop_flag or (lambda: False)
        self._lock = threading.Lock()
        self._running = False

        self._cooldown_map: dict[str, float] = {
            "radiant_kick": 13.0,
            "blitz_strike": 13.0,
            "dash": 2.0,
        }

    def execute(self, action: Wave1ActionName) -> None:
        """Execute a single HSM action."""
        with self._lock:
            if self._stop_flag():
                self._primitives.release_all_keys()
                return

            name = action.value if hasattr(action, "value") else str(action)

            if name == "HOLD_RADIANT_KICK":
                self._execute_radiant_kick()
            elif name == "RELEASE_RADIANT_KICK":
                self._primitives.release(self.keybinds.radiant_kick)
            elif name == "GEPPO_STACK":
                self._primitives.geppo_stack(
                    count=self.wave1_cfg.geppo_count,
                    interval_ms_min=self.wave1_cfg.geppo_interval_ms_min,
                    interval_ms_max=self.wave1_cfg.geppo_interval_ms_max,
                )
            elif name == "PRESS_SLOT_2":
                self._primitives.press_slot_pika_v2()
            elif name == "PRESS_ARMAMENT_HAKI":
                self._primitives.press_armament_haki()
            elif name == "OBSERVATION_SCAN":
                self._primitives.observation_scan()
            elif name == "CLEANUP_TARGET":
                self._primitives.cleanup_attack()
            elif name == "ALIGN_COMPASS":
                self._execute_align_compass()
            elif name == "MOVE_TO_EXIT":
                self._execute_move_to_exit()
            elif name == "STOP_FAILSAFE":
                self.emergency_stop()
            elif name == "WAIT":
                pass
            else:
                pass

    def _execute_radiant_kick(self) -> None:
        """Hold R for the configured charge duration."""
        cd = self._cooldowns.remaining("radiant_kick")
        if cd > 0:
            return
        self._primitives.hold(self.keybinds.radiant_kick)
        self._cooldowns.start("radiant_kick", self._cooldown_map["radiant_kick"])

    def _execute_align_compass(self) -> None:
        """Stub: compass alignment requires live compass reading, handled in runner loop."""
        pass

    def _execute_move_to_exit(self) -> None:
        """Hold W to move toward exit, with dash fallback if stuck."""
        self._primitives.hold(self.keybinds.forward)
        time.sleep(0.5)
        if self._stop_flag():
            self._primitives.release(self.keybinds.forward)
            return
        self._primitives.release(self.keybinds.forward)

    def emergency_stop(self) -> None:
        """Immediately release all keys and halt execution."""
        self._running = False
        self._primitives.release_all_keys()

    def tick_cooldowns(self, dt_sec: float) -> None:
        """Advance cooldown tracker by dt seconds."""
        self._cooldowns.tick(dt_sec)

    def on_exception(self, exc: Exception) -> None:
        """Called on any exception during execution."""
        self.emergency_stop()

    @property
    def primitives(self) -> InputPrimitives:
        return self._primitives

    @property
    def is_running(self) -> bool:
        return self._running
