"""Non-blocking input executor with deferred action queue.

Fixes:
- TAP now properly presses and releases actual keys (was a no-op).
- HOLD now waits full duration before releasing (was immediate release).
- WAIT type added for pure non-blocking delays (replaces fake key HOLDs).
- HOLD type is real key-only; no fake keys ever pressed.
- Geppo/MOVE_TO_EXIT/MOVE_TO_ENEMY/OBSERVATION_SCAN sequences use real keys + WAIT.
"""
from __future__ import annotations

import time
import threading
from typing import Callable, Literal
from dataclasses import dataclass, field
from enum import Enum

from vcl_core.config import AppConfig
from vcl_core.timebase import CooldownTracker
from vcl_input.primitives import InputPrimitives
from vcl_core.schemas import Wave1ActionName


class DeferredActionType(Enum):
    HOLD = "hold"
    TAP = "tap"
    RELEASE = "release"
    WAIT = "wait"


@dataclass
class DeferredAction:
    action_type: DeferredActionType
    key: str | None = None
    down_ms: int = 80


@dataclass
class ActionSequence:
    name: str
    steps: list[DeferredAction] = field(default_factory=list)
    _step_index: int = field(default=0, repr=False)
    _started: bool = field(default=False, repr=False)
    _subaction_start: float = field(default=0.0, repr=False)
    _holding: bool = field(default=False, repr=False)

    def start(self, now: float) -> bool:
        """Start the sequence. Returns True if needs tick processing."""
        if not self._started:
            self._started = True
            self._step_index = 0
            self._holding = False
            self._subaction_start = now
        return True

    def tick(self, primitives: InputPrimitives, now: float) -> Literal["running", "done"]:
        """
        Advance one step. Returns 'running' if more steps remain, 'done' if complete.
        Each call processes at most one deferred action.
        """
        if not self._started or self._step_index >= len(self.steps):
            return "done"

        step = self.steps[self._step_index]
        elapsed_ms = (now - self._subaction_start) * 1000.0

        if step.action_type == DeferredActionType.HOLD:
            if not self._holding:
                primitives.hold(step.key)
                self._holding = True
                self._subaction_start = now
                return "running"
            if elapsed_ms < step.down_ms:
                return "running"
            # Hold duration complete, release key and advance
            primitives.release(step.key)
            self._holding = False
            self._step_index += 1
            self._subaction_start = now
            return "running" if self._step_index < len(self.steps) else "done"

        elif step.action_type == DeferredActionType.TAP:
            if not self._holding:
                # First tick: press key
                primitives.press(step.key)
                self._holding = True
                self._subaction_start = now
                return "running"
            if elapsed_ms < step.down_ms:
                return "running"
            # Down_ms elapsed: release key and advance
            primitives.release(step.key)
            self._holding = False
            self._step_index += 1
            self._subaction_start = now
            return "running" if self._step_index < len(self.steps) else "done"

        elif step.action_type == DeferredActionType.RELEASE:
            primitives.release(step.key)
            self._step_index += 1
            self._subaction_start = now
            return "running" if self._step_index < len(self.steps) else "done"

        elif step.action_type == DeferredActionType.WAIT:
            if elapsed_ms < step.down_ms:
                return "running"
            self._step_index += 1
            self._subaction_start = now
            return "running" if self._step_index < len(self.steps) else "done"

        return "done"

    def cancel(self, primitives: InputPrimitives) -> None:
        """Release any held keys and reset."""
        if self._holding:
            key = self.steps[self._step_index].key if self._step_index < len(self.steps) else None
            if key:
                primitives.release(key)
            self._holding = False
        self._started = False
        self._step_index = 0


class InputExecutor:
    """
    Non-blocking executor that queues deferred action sequences.
    Each tick() call processes ONE step of the current sequence.
    The main capture loop is NEVER blocked by time.sleep().
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

        self._queue: list[ActionSequence] = []
        self._current: ActionSequence | None = None
        self._last_tick: float = time.monotonic()

    def execute(self, action: Wave1ActionName) -> None:
        """Enqueue an action sequence. Never blocks."""
        with self._lock:
            if self._stop_flag():
                self._primitives.release_all_keys()
                return

            name = action.value if hasattr(action, "value") else str(action)

            seq: ActionSequence | None = None

            if name == "HOLD_RADIANT_KICK":
                seq = self._build_radiant_kick_seq()
            elif name == "RELEASE_RADIANT_KICK":
                seq = self._build_release_radiant_kick_seq()
            elif name == "GEPPO_STACK":
                seq = self._build_geppo_seq()
            elif name == "PRESS_SLOT_2":
                seq = self._build_press_slot_2_seq()
            elif name == "PRESS_ARMAMENT_HAKI":
                seq = self._build_press_armament_haki_seq()
            elif name == "OBSERVATION_SCAN":
                seq = self._build_observation_scan_seq()
            elif name == "CLEANUP_TARGET":
                seq = self._build_cleanup_seq()
            elif name == "ALIGN_COMPASS":
                seq = self._build_align_compass_seq()
            elif name == "MOVE_TO_EXIT":
                seq = self._build_move_to_exit_seq()
            elif name == "MOVE_TO_ENEMY":
                seq = self._build_move_to_enemy_seq()
            elif name == "STOP_FAILSAFE":
                seq = self._build_estop_seq()
            elif name == "WAIT":
                return

            if seq is not None:
                self._queue.append(seq)

    def tick(self) -> None:
        """
        Advance the current action sequence by ONE step.
        Called once per capture frame (every ~50ms at 20fps).
        Non-blocking: processes at most one sub-action per call.
        """
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        if self._stop_flag():
            self._cancel_all()
            self._primitives.release_all_keys()
            return

        self._cooldowns.tick(dt)

        if self._current is not None:
            result = self._current.tick(self._primitives, now)
            if result == "done":
                self._current = None
            return

        if self._queue:
            self._current = self._queue.pop(0)
            self._current.start(now)
            self._current.tick(self._primitives, now)

    def _build_radiant_kick_seq(self) -> ActionSequence:
        """Hold R for radiant_kick_charge_ms then release."""
        charge_ms = self.wave1_cfg.radiant_kick_charge_ms
        cd = self._cooldowns.remaining("radiant_kick")
        if cd > 0:
            return ActionSequence(name="radiant_kick_cd_skip", steps=[])
        return ActionSequence(
            name="radiant_kick",
            steps=[
                DeferredAction(DeferredActionType.HOLD, self.keybinds.radiant_kick, charge_ms),
                DeferredAction(DeferredActionType.RELEASE, self.keybinds.radiant_kick),
            ],
        )

    def _build_release_radiant_kick_seq(self) -> ActionSequence:
        return ActionSequence(
            name="release_radiant_kick",
            steps=[DeferredAction(DeferredActionType.RELEASE, self.keybinds.radiant_kick)],
        )

    def _build_geppo_seq(self) -> ActionSequence:
        """Geppo: rapid Space taps while holding backward (S). Non-blocking.

        Pattern: HOLD backward -> TAP jump -> WAIT interval -> ... -> RELEASE backward
        No fake keys ever pressed.
        """
        import random
        count = self.wave1_cfg.geppo_count
        interval_min = self.wave1_cfg.geppo_interval_ms_min
        interval_max = self.wave1_cfg.geppo_interval_ms_max

        steps: list[DeferredAction] = [
            DeferredAction(DeferredActionType.HOLD, self.keybinds.backward),
        ]
        for i in range(count):
            interval_ms = int(random.uniform(interval_min, interval_max))
            steps.append(DeferredAction(DeferredActionType.TAP, self.keybinds.jump, 60))
            steps.append(DeferredAction(DeferredActionType.WAIT, down_ms=interval_ms))
        steps.append(DeferredAction(DeferredActionType.RELEASE, self.keybinds.backward))
        return ActionSequence(name="geppo", steps=steps)

    def _build_press_slot_2_seq(self) -> ActionSequence:
        return ActionSequence(
            name="press_slot_2",
            steps=[DeferredAction(DeferredActionType.TAP, self.keybinds.slot_pika_v2, 80)],
        )

    def _build_press_armament_haki_seq(self) -> ActionSequence:
        return ActionSequence(
            name="press_armament_haki",
            steps=[DeferredAction(DeferredActionType.TAP, self.keybinds.armament_haki, 80)],
        )

    def _build_observation_scan_seq(self) -> ActionSequence:
        """Observation scan: tap G then wait for scan to complete. No fake keys."""
        scan_ms = self.config.observation_haki.scan_duration_ms
        return ActionSequence(
            name="observation_scan",
            steps=[
                DeferredAction(DeferredActionType.TAP, self.keybinds.observation_haki, 80),
                DeferredAction(DeferredActionType.WAIT, down_ms=scan_ms),
            ],
        )

    def _build_cleanup_seq(self) -> ActionSequence:
        """Blitz strike: tap 1 to select slot, tap E for blitz strike."""
        return ActionSequence(
            name="cleanup",
            steps=[
                DeferredAction(DeferredActionType.TAP, "1", 200),
                DeferredAction(DeferredActionType.TAP, self.keybinds.blitz_strike, 200),
            ],
        )

    def _build_align_compass_seq(self) -> ActionSequence:
        return ActionSequence(name="align_compass", steps=[])

    def _build_move_to_exit_seq(self) -> ActionSequence:
        """Move forward: HOLD forward, WAIT for movement duration, RELEASE forward."""
        move_ms = self.config.wave1.damage_register_wait_ms
        return ActionSequence(
            name="move_to_exit",
            steps=[
                DeferredAction(DeferredActionType.HOLD, self.keybinds.forward),
                DeferredAction(DeferredActionType.WAIT, down_ms=move_ms),
                DeferredAction(DeferredActionType.RELEASE, self.keybinds.forward),
            ],
        )

    def _build_move_to_enemy_seq(self) -> ActionSequence:
        """Move backward: HOLD backward, WAIT for movement duration, RELEASE backward."""
        move_ms = self.config.wave1.damage_register_wait_ms
        return ActionSequence(
            name="move_to_enemy",
            steps=[
                DeferredAction(DeferredActionType.HOLD, self.keybinds.backward),
                DeferredAction(DeferredActionType.WAIT, down_ms=move_ms),
                DeferredAction(DeferredActionType.RELEASE, self.keybinds.backward),
            ],
        )

    def _build_estop_seq(self) -> ActionSequence:
        return ActionSequence(name="estop", steps=[])

    def _cancel_all(self) -> None:
        if self._current:
            self._current.cancel(self._primitives)
            self._current = None
        for seq in self._queue:
            seq.cancel(self._primitives)
        self._queue.clear()

    def emergency_stop(self) -> None:
        """Immediately cancel all pending actions and halt."""
        self._running = False
        with self._lock:
            self._cancel_all()
        self._primitives.release_all_keys()

    def tick_cooldowns(self, dt_sec: float) -> None:
        self._cooldowns.tick(dt_sec)

    def on_exception(self, exc: Exception) -> None:
        self.emergency_stop()

    @property
    def primitives(self) -> InputPrimitives:
        return self._primitives

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_idle(self) -> bool:
        """True if no actions are in flight."""
        return self._current is None and len(self._queue) == 0
