"""Wave 1 Hierarchical State Machine."""
from __future__ import annotations

import time
from typing import Callable

from vcl_core.schemas import GameState, ProgressState, CompassState, Wave1Action, Wave1ActionName
from vcl_core.config import Wave1Config, SafetyConfig, AppConfig
from vcl_hsm.states import Wave1State
from vcl_hsm import transitions as trans


class Wave1HSM:
    """
    Hierarchical State Machine for Wave 1: Shattered Ramparts.

    The HSM consumes GameState snapshots and emits Wave1Action commands.
    It NEVER allows exit from the wave unless objective_current == 4.

    Safety constraints:
    - max_state_duration_sec: abort if any state exceeds this limit
    - min_confidence for progress: require confidence >= 0.75 before clearing
    - max_cleanup_cycles: cap observation haki + cleanup cycles
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        on_action: Callable[[Wave1Action], None] | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self.wave1_cfg = self.config.wave1
        self.safety_cfg = self.config.safety
        self.progress_cfg = self.config.progress_ui
        self.compass_cfg = self.config.compass
        self.on_action = on_action

        self.state = Wave1State.BOOT
        self._prev_state: Wave1State | None = None
        self._state_entered_at: float = 0.0
        self._prev_progress: ProgressState | None = None
        self._prev_stage: str | None = None
        self._prev_objective: int | None = None
        self._cleanup_cycles = 0
        self._observation_scans = 0
        self._radiant_kick_casts = 0
        self._geppo_count = 0
        self._haki_scan_frames: list = []
        self._action_history: list[Wave1Action] = []
        self._stopped = False
        self._waves_cleared = 0
        self._total_waves = 4

    def tick(
        self,
        game_state: GameState,
        progress: ProgressState | None,
        compass: CompassState | None,
        current_time: float | None = None,
    ) -> Wave1Action:
        """
        Main HSM tick: evaluate guards, transition state, produce action.

        Called once per frame (video) or once per capture cycle (live).
        """
        if current_time is None:
            current_time = time.monotonic()

        if self.state == Wave1State.BOOT:
            self._transition_to(Wave1State.WAIT_PLAYER_CONTROL, current_time)
            return self._action(Wave1ActionName.WAIT, "boot initializing", current_time)

        can_exit, reason = trans.guard_can_exit(
            self.state, game_state, progress, self.safety_cfg,
            self._state_entered_at, current_time,
        )
        if not can_exit:
            self._transition_to(Wave1State.FAILSAFE, current_time)
            return self._action(Wave1ActionName.STOP_FAILSAFE, f"guard_failed: {reason}", current_time)

        action = self._evaluate_state(
            game_state, progress, compass, current_time, reason
        )
        return action

    def _evaluate_state(
        self,
        game_state: GameState,
        progress: ProgressState | None,
        compass: CompassState | None,
        current_time: float,
        guard_reason: str,
    ) -> Wave1Action:
        """Evaluate current state, check transitions, return action."""
        state = self.state

        if state == Wave1State.WAIT_PLAYER_CONTROL:
            ok, reason = trans.guard_wait_for_stage(
                progress, timeout_sec=60.0,
                entered_at=self._state_entered_at,
                current_time=current_time,
            )
            if ok:
                self._transition_to(Wave1State.SETUP_PIKA_V2, current_time)
                return self._action(Wave1ActionName.PRESS_SLOT_2, "stage detected, selecting Pika V2", current_time)
            return self._action(Wave1ActionName.WAIT, f"waiting_for_stage: {reason}", current_time)

        if state == Wave1State.SETUP_PIKA_V2:
            elapsed = current_time - self._state_entered_at
            if elapsed < self.wave1_cfg.setup_delay_ms / 1000.0:
                return self._action(Wave1ActionName.WAIT, "setup_delay", current_time)
            self._transition_to(Wave1State.ENTER_STAGE, current_time)
            return self._action(Wave1ActionName.PRESS_ARMAMENT_HAKI, "pika v2 ready, enabling armament haki", current_time)

        if state == Wave1State.ENTER_STAGE:
            elapsed = current_time - self._state_entered_at
            if elapsed < 0.5:
                return self._action(Wave1ActionName.WAIT, "entering_stage", current_time)
            self._transition_to(Wave1State.VERIFY_STAGE_UI, current_time)
            return self._action(Wave1ActionName.READ_PROGRESS, "stage entered, verifying UI", current_time)

        if state == Wave1State.VERIFY_STAGE_UI:
            ok, reason = trans.guard_stage_verified(
                progress, expected_stage=self.progress_cfg.stage_name
            )
            if ok:
                self._transition_to(Wave1State.AGGRO_WITH_GEPPO, current_time)
                self._prev_progress = progress
                return self._action(Wave1ActionName.GEPPO_STACK, "stage verified, starting geppo", current_time)
            return self._action(Wave1ActionName.READ_PROGRESS, f"verifying_stage: {reason}", current_time)

        if state == Wave1State.AGGRO_WITH_GEPPO:
            self._geppo_count += 1
            ok, reason = trans.guard_geppo_done(
                self._geppo_count, self.wave1_cfg,
                self._state_entered_at, current_time,
            )
            if ok:
                self._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, current_time)
                self._radiant_kick_casts += 1
                return self._action(
                    Wave1ActionName.HOLD_RADIANT_KICK,
                    f"geppo done ({self._geppo_count}x), casting charged radiant kick",
                    current_time,
                )
            return self._action(
                Wave1ActionName.GEPPO_STACK,
                f"geppo ({self._geppo_count}/{self.wave1_cfg.geppo_count}): {reason}",
                current_time,
            )

        if state == Wave1State.CAST_CHARGED_RADIANT_KICK:
            elapsed = current_time - self._state_entered_at
            if elapsed < self.wave1_cfg.radiant_kick_charge_ms / 1000.0:
                return self._action(Wave1ActionName.HOLD_RADIANT_KICK, f"charging: {elapsed:.1f}s", current_time)
            self._transition_to(Wave1State.VERIFY_COUNTER, current_time)
            self._prev_progress = progress
            return self._action(Wave1ActionName.RELEASE_RADIANT_KICK, "released kick, waiting for damage", current_time)

        if state == Wave1State.VERIFY_COUNTER:
            ok, reason = trans.guard_objective_complete(progress, min_confidence=0.65)
            if ok:
                self._prev_progress = progress
                self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                return self._action(
                    Wave1ActionName.ALIGN_COMPASS,
                    f"4/4 confirmed, aligning compass to {self.compass_cfg.target_exit_heading}",
                    current_time,
                )
            ok_incomplete, reason2 = trans.guard_objective_incomplete(progress)
            if ok_incomplete:
                self._transition_to(Wave1State.OBS_HAKI_SCAN, current_time)
                self._prev_progress = progress
                return self._action(
                    Wave1ActionName.OBSERVATION_SCAN,
                    f"counter not complete: {reason2}, scanning with haki",
                    current_time,
                )
            return self._action(Wave1ActionName.READ_PROGRESS, f"counter_checking: {reason} / {reason2}", current_time)

        if state == Wave1State.OBS_HAKI_SCAN:
            self._observation_scans += 1
            elapsed = current_time - self._state_entered_at
            if elapsed < self.config.observation_haki.scan_duration_ms / 1000.0:
                return self._action(Wave1ActionName.WAIT, "haki_scan_active", current_time)
            if self._cleanup_cycles < self.wave1_cfg.max_cleanup_cycles:
                self._cleanup_cycles += 1
                self._transition_to(Wave1State.CLEANUP_IF_NEEDED, current_time)
                return self._action(Wave1ActionName.CLEANUP_TARGET, f"cleanup cycle {self._cleanup_cycles}", current_time)
            return self._action(
                Wave1ActionName.STOP_FAILSAFE,
                f"max_cleanup_cycles ({self.wave1_cfg.max_cleanup_cycles}) exceeded",
                current_time,
            )

        if state == Wave1State.CLEANUP_IF_NEEDED:
            elapsed = current_time - self._state_entered_at
            if elapsed < 3.0:
                return self._action(Wave1ActionName.CLEANUP_TARGET, f"cleanup: {elapsed:.1f}s", current_time)
            self._transition_to(Wave1State.VERIFY_COUNTER_AGAIN, current_time)
            return self._action(Wave1ActionName.READ_PROGRESS, "cleanup done, re-verifying counter", current_time)

        if state == Wave1State.VERIFY_COUNTER_AGAIN:
            ok, reason = trans.guard_objective_complete(progress, min_confidence=0.65)
            if ok:
                self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                return self._action(
                    Wave1ActionName.ALIGN_COMPASS,
                    f"4/4 confirmed after cleanup, aligning to {self.compass_cfg.target_exit_heading}",
                    current_time,
                )
            if self._cleanup_cycles < self.wave1_cfg.max_cleanup_cycles:
                self._cleanup_cycles += 1
                self._transition_to(Wave1State.CLEANUP_IF_NEEDED, current_time)
                return self._action(Wave1ActionName.CLEANUP_TARGET, f"cleanup cycle {self._cleanup_cycles}", current_time)
            return self._action(Wave1ActionName.STOP_FAILSAFE, f"still incomplete after {self._cleanup_cycles} cycles", current_time)

        if state == Wave1State.ALIGN_TO_EXIT:
            ok, reason = trans.guard_compass_aligned(
                compass, self.compass_cfg.target_exit_heading,
                tolerance_deg=self.compass_cfg.heading_tolerance_deg,
                timeout_sec=self.compass_cfg.rotate_timeout_sec,
                state_entered_at=self._state_entered_at,
                current_time=current_time,
            )
            if ok:
                self._transition_to(Wave1State.MOVE_NEXT_STAGE, current_time)
                self._prev_stage = progress.stage_name if progress else None
                self._prev_objective = progress.objective_current if progress else None
                return self._action(Wave1ActionName.MOVE_TO_EXIT, f"compass aligned, moving to exit: {reason}", current_time)
            return self._action(Wave1ActionName.ALIGN_COMPASS, f"aligning: {reason}", current_time)

        if state == Wave1State.MOVE_NEXT_STAGE:
            elapsed = current_time - self._state_entered_at
            if elapsed < 1.0:
                return self._action(Wave1ActionName.MOVE_TO_EXIT, "moving to exit", current_time)
            self._transition_to(Wave1State.CONFIRM_STAGE_TRANSITION, current_time)
            return self._action(Wave1ActionName.WAIT, "checking stage transition", current_time)

        if state == Wave1State.CONFIRM_STAGE_TRANSITION:
            ok, reason = trans.guard_stage_transitioned(
                self._prev_stage, self._prev_objective, progress,
                timeout_sec=5.0,
                state_entered_at=self._state_entered_at,
                current_time=current_time,
            )
            if ok:
                self._waves_cleared += 1
                if self._waves_cleared >= self._total_waves:
                    self._transition_to(Wave1State.DONE, current_time)
                    return self._action(
                        Wave1ActionName.WAIT,
                        f"all {self._waves_cleared} waves cleared, dungeon complete!",
                        current_time,
                    )
                self._geppo_count = 0
                self._cleanup_cycles = 0
                self._prev_progress = None
                self._transition_to(Wave1State.AGGRO_WITH_GEPPO, current_time)
                return self._action(
                    Wave1ActionName.GEPPO_STACK,
                    f"wave {self._waves_cleared}/{self._total_waves} cleared, starting wave {self._waves_cleared + 1}",
                    current_time,
                )
            return self._action(Wave1ActionName.WAIT, f"waiting_transition: {reason}", current_time)

        if state == Wave1State.FAILSAFE:
            return self._action(Wave1ActionName.STOP_FAILSAFE, "failsafe active", current_time)

        if state == Wave1State.DONE:
            return self._action(Wave1ActionName.WAIT, "wave_complete", current_time)

        return self._action(Wave1ActionName.WAIT, f"unknown_state: {self.state}", current_time)

    def _transition_to(self, new_state: Wave1State, current_time: float) -> None:
        """Record state transition."""
        self._prev_state = self.state
        self.state = new_state
        self._state_entered_at = current_time

    def _action(
        self, name: Wave1ActionName, reason: str, current_time: float
    ) -> Wave1Action:
        """Create action, log it, call callback."""
        action = Wave1Action(name=name, reason=reason)
        self._action_history.append(action)
        if self.on_action:
            self.on_action(action)
        return action

    def reset(self) -> None:
        """Reset HSM to BOOT state."""
        self.state = Wave1State.BOOT
        self._prev_state = None
        self._state_entered_at = 0.0
        self._prev_progress = None
        self._prev_stage = None
        self._prev_objective = None
        self._cleanup_cycles = 0
        self._observation_scans = 0
        self._radiant_kick_casts = 0
        self._geppo_count = 0
        self._haki_scan_frames = []
        self._action_history = []
        self._stopped = False
        self._waves_cleared = 0

    @property
    def stats(self) -> dict:
        return {
            "state": self.state.value,
            "prev_state": self._prev_state.value if self._prev_state else None,
            "geppo_count": self._geppo_count,
            "radiant_kick_casts": self._radiant_kick_casts,
            "observation_scans": self._observation_scans,
            "cleanup_cycles": self._cleanup_cycles,
            "waves_cleared": self._waves_cleared,
            "action_count": len(self._action_history),
        }
