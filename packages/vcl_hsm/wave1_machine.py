"""Wave 1 Hierarchical State Machine — Shattered Ramparts only."""
from __future__ import annotations

import time
from typing import Callable

from vcl_core.schemas import GameState, ProgressState, CompassState, Wave1Action, Wave1ActionName
from vcl_core.config import Wave1Config, SafetyConfig, AppConfig
from vcl_hsm.states import Wave1State
from vcl_hsm.transitions import (
    guard_can_exit,
    guard_wait_for_stage,
    guard_stage_verified,
    guard_geppo_done,
    guard_damage_registered,
    guard_objective_complete,
    guard_objective_incomplete,
    guard_compass_aligned,
    guard_stage_transitioned,
)
from vcl_hsm.stability import CounterStabilityTracker


class Wave1HSM:
    """
    Hierarchical State Machine for Wave 1: Shattered Ramparts only.

    This HSM finishes after Wave 1 clear and transition confirmation.
    It does NOT loop through multiple waves.

    Safety constraints:
    - max_state_duration_sec: abort if any state exceeds this limit
    - CounterStabilityTracker: require 3 consecutive 4/4 reads before exit
    - min_confidence for progress: require confidence >= 0.75 before clearing
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
        self._haki_scan_frames: list = []
        self._action_history: list[Wave1Action] = []
        self._stopped = False

        self._stability = CounterStabilityTracker(
            window_size=self.wave1_cfg.stable_window_size,
            required_count=self.wave1_cfg.stable_required_count,
            required_objective=self.progress_cfg.objective_total,
            min_confidence=self.progress_cfg.min_confidence,
            persistent_window_size=self.wave1_cfg.persistent_window_size,
            persistent_required_total=self.wave1_cfg.persistent_required_total,
            persistent_required_strong=self.wave1_cfg.persistent_required_strong,
            persistent_min_strong_confidence=self.progress_cfg.min_confidence,
        )

        self._action_emitted: set[str] = set()
        self._compass_forced = False
        self._radiant_released_at: float | None = None
        self._state_entry_id: int = 0

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
            return self._emit_action_once(
                Wave1State.WAIT_PLAYER_CONTROL,
                Wave1ActionName.WAIT,
                "boot initializing",
                current_time,
            )

        can_exit, reason = guard_can_exit(
            self.state, game_state, progress, self.safety_cfg,
            self._state_entered_at, current_time,
        )
        if not can_exit:
            self._transition_to(Wave1State.FAILSAFE, current_time)
            return self._emit_action_once(
                Wave1State.FAILSAFE,
                Wave1ActionName.STOP_FAILSAFE,
                f"guard_failed: {reason}",
                current_time,
            )

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
        """Evaluate current state, check transitions, return one-shot action."""
        state = self.state

        if state == Wave1State.WAIT_PLAYER_CONTROL:
            ok, reason = guard_wait_for_stage(
                progress, timeout_sec=60.0,
                entered_at=self._state_entered_at,
                current_time=current_time,
            )
            if ok:
                self._transition_to(Wave1State.SETUP_PIKA_V2, current_time)
                return self._emit_action_once(
                    Wave1State.SETUP_PIKA_V2,
                    Wave1ActionName.PRESS_SLOT_2,
                    "stage detected, selecting Pika V2",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.WAIT_PLAYER_CONTROL,
                Wave1ActionName.WAIT,
                f"waiting_for_stage: {reason}",
                current_time,
            )

        if state == Wave1State.SETUP_PIKA_V2:
            elapsed = current_time - self._state_entered_at
            if elapsed < self.wave1_cfg.setup_delay_ms / 1000.0:
                return self._emit_action_once(
                    Wave1State.SETUP_PIKA_V2,
                    Wave1ActionName.WAIT,
                    "setup_delay",
                    current_time,
                )
            self._transition_to(Wave1State.ENTER_STAGE, current_time)
            return self._emit_action_once(
                Wave1State.ENTER_STAGE,
                Wave1ActionName.PRESS_ARMAMENT_HAKI,
                "pika v2 ready, enabling armament haki",
                current_time,
            )

        if state == Wave1State.ENTER_STAGE:
            elapsed = current_time - self._state_entered_at
            if elapsed < 0.5:
                return self._emit_action_once(
                    Wave1State.ENTER_STAGE,
                    Wave1ActionName.WAIT,
                    "entering_stage",
                    current_time,
                )
            self._transition_to(Wave1State.VERIFY_STAGE_UI, current_time)
            return self._emit_action_once(
                Wave1State.VERIFY_STAGE_UI,
                Wave1ActionName.READ_PROGRESS,
                "stage entered, verifying UI",
                current_time,
            )

        if state == Wave1State.VERIFY_STAGE_UI:
            ok, reason = guard_stage_verified(
                progress,
                expected_stage=self.progress_cfg.stage_name,
                min_confidence=self.progress_cfg.min_confidence,
                initial_counter_max=self.wave1_cfg.initial_counter_max,
            )
            if ok:
                self._transition_to(Wave1State.AGGRO_WITH_GEPPO, current_time)
                self._prev_progress = progress
                return self._emit_action_once(
                    Wave1State.AGGRO_WITH_GEPPO,
                    Wave1ActionName.GEPPO_STACK,
                    f"stage verified, starting geppo ({self.wave1_cfg.geppo_count}x)",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.VERIFY_STAGE_UI,
                Wave1ActionName.READ_PROGRESS,
                f"verifying_stage_ui: {reason}",
                current_time,
            )

        if state == Wave1State.AGGRO_WITH_GEPPO:
            elapsed = current_time - self._state_entered_at
            ok, reason = guard_geppo_done(
                self.wave1_cfg.geppo_count, self.wave1_cfg,
                self._state_entered_at, current_time,
            )
            if ok:
                self._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, current_time)
                self._radiant_kick_casts += 1
                return self._emit_action_once(
                    Wave1State.CAST_CHARGED_RADIANT_KICK,
                    Wave1ActionName.HOLD_RADIANT_KICK,
                    f"geppo done ({self.wave1_cfg.geppo_count}x), casting charged radiant kick",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.AGGRO_WITH_GEPPO,
                Wave1ActionName.GEPPO_STACK,
                f"aggro_wait: {elapsed:.1f}s (geppo count={self.wave1_cfg.geppo_count})",
                current_time,
            )

        if state == Wave1State.CAST_CHARGED_RADIANT_KICK:
            elapsed = current_time - self._state_entered_at
            if elapsed < self.wave1_cfg.radiant_kick_charge_ms / 1000.0:
                return self._emit_action_once(
                    Wave1State.CAST_CHARGED_RADIANT_KICK,
                    Wave1ActionName.HOLD_RADIANT_KICK,
                    f"charging: {elapsed:.1f}s",
                    current_time,
                )

            self._transition_to(Wave1State.RELEASE_RADIANT_KICK, current_time)
            self._radiant_released_at = current_time
            return self._emit_action_once(
                Wave1State.RELEASE_RADIANT_KICK,
                Wave1ActionName.RELEASE_RADIANT_KICK,
                f"charge done at {elapsed:.1f}s, releasing",
                current_time,
            )

        if state == Wave1State.RELEASE_RADIANT_KICK:
            wait_elapsed = current_time - self._radiant_released_at
            wait_required = self.wave1_cfg.damage_register_wait_ms / 1000.0
            if wait_elapsed < wait_required:
                return self._emit_action_once(
                    Wave1State.RELEASE_RADIANT_KICK,
                    Wave1ActionName.WAIT,
                    f"waiting_damage_register: {wait_elapsed:.1f}s/{wait_required:.1f}s",
                    current_time,
                )

            self._radiant_released_at = None
            self._transition_to(Wave1State.VERIFY_COUNTER, current_time)
            self._prev_progress = progress
            self._stability.reset()
            return self._emit_action_once(
                Wave1State.VERIFY_COUNTER,
                Wave1ActionName.READ_PROGRESS,
                f"damage registered, verifying counter",
                current_time,
            )

        if state == Wave1State.VERIFY_COUNTER:
            self._stability.update(
                progress.objective_current if progress else None,
                progress.objective_total if progress else None,
                progress.confidence if progress else 0.0,
            )

            ok_complete, reason = guard_objective_complete(
                progress, min_confidence=self.progress_cfg.min_confidence
            )
            if ok_complete:
                if self._stability.is_stable_clear():
                    self._prev_progress = progress
                    self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                    return self._emit_action_once(
                        Wave1State.ALIGN_TO_EXIT,
                        Wave1ActionName.ALIGN_COMPASS,
                        f"stable 4/4 confirmed, aligning compass to {self.compass_cfg.target_exit_heading}",
                        current_time,
                    )
                strong_count = len([r for r in self._stability.last_reads if r[0] == 4 and r[1] >= self.progress_cfg.min_confidence])
                return self._emit_action_once(
                    Wave1State.VERIFY_COUNTER,
                    Wave1ActionName.WAIT,
                    f"4/4 seen but not yet stable ({strong_count}/{self.wave1_cfg.stable_required_count})",
                    current_time,
                )

            # Reject impossible counter drops during verification.
            # A 4/4 -> 0/4 transition without stage context is noise/flicker.
            if progress and self._stability.is_impossible_drop(
                progress.objective_current,
                progress.objective_total,
                progress.confidence if progress else 0.0,
            ):
                return self._emit_action_once(
                    Wave1State.VERIFY_COUNTER,
                    Wave1ActionName.WAIT,
                    "rejected_impossible_drop",
                    current_time,
                )

            elapsed = current_time - self._state_entered_at
            verify_window = self.wave1_cfg.verify_window_sec

            # PERSISTENT CLEAR FALLBACK: if the persistent window shows consistent 4/4
            # with intermittent confidence, exit to ALIGN_TO_EXIT without waiting for
            # verify_window to expire. This prevents FAILSAFE on real captures where
            # per-frame confidence flickers but the count is visibly consistent.
            persistent_reads = self._stability.persistent_reads
            at_4_in_persistent = [r for r in persistent_reads if r[0] == 4]
            strong_in_persistent = [r for r in persistent_reads if r[0] == 4 and r[1] >= self.progress_cfg.min_confidence]
            if (
                len(at_4_in_persistent) >= self.wave1_cfg.persistent_required_total
                and len(strong_in_persistent) >= self.wave1_cfg.persistent_required_strong
            ):
                self._prev_progress = progress
                self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                return self._emit_action_once(
                    Wave1State.ALIGN_TO_EXIT,
                    Wave1ActionName.ALIGN_COMPASS,
                    f"persistent 4/4 confirmed ({len(at_4_in_persistent)}/{len(persistent_reads)} reads, "
                    f"{len(strong_in_persistent)} high-confidence anchors), aligning to {self.compass_cfg.target_exit_heading}",
                    current_time,
                )

            if elapsed < verify_window:
                weak_count = len(at_4_in_persistent)
                strong_count = len(strong_in_persistent)
                return self._emit_action_once(
                    Wave1State.VERIFY_COUNTER,
                    Wave1ActionName.WAIT,
                    f"verifying ({elapsed:.1f}s < {verify_window:.1f}s window, "
                    f"{weak_count}/{len(persistent_reads)} reads, {strong_count} anchors)",
                    current_time,
                )

            # Window expired: route to cleanup
            ok_incomplete, reason2 = guard_objective_incomplete(progress)
            if ok_incomplete:
                self._transition_to(Wave1State.OBS_HAKI_SCAN, current_time)
                self._prev_progress = progress
                self._stability.reset()
                return self._emit_action_once(
                    Wave1State.OBS_HAKI_SCAN,
                    Wave1ActionName.OBSERVATION_SCAN,
                    f"counter not complete: {reason2}, scanning with haki",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.VERIFY_COUNTER,
                Wave1ActionName.READ_PROGRESS,
                f"counter_checking: {reason} / {reason2}",
                current_time,
            )

        if state == Wave1State.OBS_HAKI_SCAN:
            # Update stability tracker during scan.
            # If stable 4/4 appears, exit to ALIGN_TO_EXIT immediately.
            self._stability.update(
                progress.objective_current if progress else None,
                progress.objective_total if progress else None,
                progress.confidence if progress else None,
            )

            # Reject impossible counter drops (e.g., 4/4 -> 0/4) during scan.
            # If we previously saw high count and now see 0/4, treat as flicker/noise.
            if progress and self._stability.is_impossible_drop(
                progress.objective_current,
                progress.objective_total,
                progress.confidence if progress else 0.0,
            ):
                return self._emit_action_once(
                    Wave1State.OBS_HAKI_SCAN,
                    Wave1ActionName.WAIT,
                    "rejected_impossible_drop",
                    current_time,
                )

            if self._stability.is_stable_clear():
                self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                return self._emit_action_once(
                    Wave1State.ALIGN_TO_EXIT,
                    Wave1ActionName.ALIGN_COMPASS,
                    "stable 4/4 during haki scan, exiting early",
                    current_time,
                )

            elapsed = current_time - self._state_entered_at
            scan_window = self.config.observation_haki.scan_duration_ms / 1000.0
            if elapsed < scan_window:
                return self._emit_action_once(
                    Wave1State.OBS_HAKI_SCAN,
                    Wave1ActionName.WAIT,
                    "haki_scan_active",
                    current_time,
                )
            if self._cleanup_cycles < self.wave1_cfg.max_cleanup_cycles:
                self._cleanup_cycles += 1
                self._transition_to(Wave1State.CLEANUP_IF_NEEDED, current_time)
                return self._emit_action_once(
                    Wave1State.CLEANUP_IF_NEEDED,
                    Wave1ActionName.CLEANUP_TARGET,
                    f"cleanup cycle {self._cleanup_cycles}/{self.wave1_cfg.max_cleanup_cycles}",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.FAILSAFE,
                Wave1ActionName.STOP_FAILSAFE,
                f"max_cleanup_cycles ({self.wave1_cfg.max_cleanup_cycles}) exceeded",
                current_time,
            )

        if state == Wave1State.CLEANUP_IF_NEEDED:
            elapsed = current_time - self._state_entered_at
            if elapsed < 3.0:
                return self._emit_action_once(
                    Wave1State.CLEANUP_IF_NEEDED,
                    Wave1ActionName.WAIT,
                    f"cleanup: {elapsed:.1f}s",
                    current_time,
                )
            self._transition_to(Wave1State.VERIFY_COUNTER_AGAIN, current_time)
            return self._emit_action_once(
                Wave1State.VERIFY_COUNTER_AGAIN,
                Wave1ActionName.READ_PROGRESS,
                "cleanup done, re-verifying counter",
                current_time,
            )

        if state == Wave1State.VERIFY_COUNTER_AGAIN:
            self._stability.update(
                progress.objective_current if progress else None,
                progress.objective_total if progress else None,
                progress.confidence if progress else 0.0,
            )

            ok_complete, _ = guard_objective_complete(progress, min_confidence=self.progress_cfg.min_confidence)
            if ok_complete:
                if self._stability.is_stable_clear():
                    self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                    return self._emit_action_once(
                        Wave1State.ALIGN_TO_EXIT,
                        Wave1ActionName.ALIGN_COMPASS,
                        f"stable 4/4 confirmed after cleanup, aligning to {self.compass_cfg.target_exit_heading}",
                        current_time,
                    )
                strong_count = len([r for r in self._stability.last_reads if r[0] == 4 and r[1] >= self.progress_cfg.min_confidence])
                return self._emit_action_once(
                    Wave1State.VERIFY_COUNTER_AGAIN,
                    Wave1ActionName.WAIT,
                    f"4/4 after cleanup but not stable ({strong_count}/{self.wave1_cfg.stable_required_count})",
                    current_time,
                )

            # PERSISTENT CLEAR FALLBACK for VERIFY_COUNTER_AGAIN
            at_4_in_persistent = [r for r in self._stability.persistent_reads if r[0] == 4]
            strong_in_persistent = [r for r in self._stability.persistent_reads if r[0] == 4 and r[1] >= self.progress_cfg.min_confidence]
            if (
                len(at_4_in_persistent) >= self.wave1_cfg.persistent_required_total
                and len(strong_in_persistent) >= self.wave1_cfg.persistent_required_strong
            ):
                self._transition_to(Wave1State.ALIGN_TO_EXIT, current_time)
                return self._emit_action_once(
                    Wave1State.ALIGN_TO_EXIT,
                    Wave1ActionName.ALIGN_COMPASS,
                    f"persistent 4/4 confirmed after cleanup ({len(at_4_in_persistent)}/{len(self._stability.persistent_reads)} reads, "
                    f"{len(strong_in_persistent)} anchors), aligning to {self.compass_cfg.target_exit_heading}",
                    current_time,
                )

            if self._cleanup_cycles < self.wave1_cfg.max_cleanup_cycles:
                self._cleanup_cycles += 1
                self._transition_to(Wave1State.CLEANUP_IF_NEEDED, current_time)
                return self._emit_action_once(
                    Wave1State.CLEANUP_IF_NEEDED,
                    Wave1ActionName.CLEANUP_TARGET,
                    f"cleanup cycle {self._cleanup_cycles}/{self.wave1_cfg.max_cleanup_cycles}",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.FAILSAFE,
                Wave1ActionName.STOP_FAILSAFE,
                f"still incomplete after {self._cleanup_cycles} cycles",
                current_time,
            )

        if state == Wave1State.ALIGN_TO_EXIT:
            ok, reason = guard_compass_aligned(
                compass, self.compass_cfg.target_exit_heading,
                tolerance_deg=self.compass_cfg.heading_tolerance_deg,
                timeout_sec=self.compass_cfg.rotate_timeout_sec,
                state_entered_at=self._state_entered_at,
                current_time=current_time,
            )
            elapsed = current_time - self._state_entered_at
            if ok or (elapsed > self.compass_cfg.rotate_timeout_sec and not self._compass_forced):
                self._compass_forced = True
                self._transition_to(Wave1State.MOVE_NEXT_STAGE, current_time)
                self._prev_stage = progress.stage_name if progress else None
                self._prev_objective = progress.objective_current if progress else None
                align_note = "" if ok else " (compass forced — no reading)"
                return self._emit_action_once(
                    Wave1State.MOVE_NEXT_STAGE,
                    Wave1ActionName.MOVE_TO_EXIT,
                    f"{'compass aligned' if ok else 'compass timeout'}{align_note}: {reason}",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.ALIGN_TO_EXIT,
                Wave1ActionName.ALIGN_COMPASS,
                f"aligning: {reason}",
                current_time,
            )

        if state == Wave1State.MOVE_NEXT_STAGE:
            elapsed = current_time - self._state_entered_at
            if elapsed < 1.0:
                return self._emit_action_once(
                    Wave1State.MOVE_NEXT_STAGE,
                    Wave1ActionName.WAIT,
                    "moving_to_exit",
                    current_time,
                )
            self._transition_to(Wave1State.CONFIRM_STAGE_TRANSITION, current_time)
            return self._emit_action_once(
                Wave1State.CONFIRM_STAGE_TRANSITION,
                Wave1ActionName.WAIT,
                "checking stage transition",
                current_time,
            )

        if state == Wave1State.CONFIRM_STAGE_TRANSITION:
            ok, reason = guard_stage_transitioned(
                self._prev_stage, self._prev_objective, progress,
                expected_next_stage=self.wave1_cfg.next_stage_name,
                timeout_sec=5.0,
                state_entered_at=self._state_entered_at,
                current_time=current_time,
            )
            if ok:
                self._transition_to(Wave1State.DONE, current_time)
                return self._emit_action_once(
                    Wave1State.DONE,
                    Wave1ActionName.WAIT,
                    f"wave 1 cleared, transitioned from {self._prev_stage} to {progress.stage_name if progress else '?'}",
                    current_time,
                )
            return self._emit_action_once(
                Wave1State.CONFIRM_STAGE_TRANSITION,
                Wave1ActionName.WAIT,
                f"waiting_transition: {reason}",
                current_time,
            )

        if state == Wave1State.FAILSAFE:
            return self._emit_action_once(
                Wave1State.FAILSAFE,
                Wave1ActionName.STOP_FAILSAFE,
                "failsafe active",
                current_time,
            )

        if state == Wave1State.DONE:
            return self._emit_action_once(
                Wave1State.DONE,
                Wave1ActionName.WAIT,
                "wave_complete",
                current_time,
            )

        return self._emit_action_once(
            self.state,
            Wave1ActionName.WAIT,
            f"unknown_state: {self.state}",
            current_time,
        )

    def _emit_action_once(
        self,
        state: Wave1State,
        name: Wave1ActionName,
        reason: str,
        current_time: float,
    ) -> Wave1Action:
        """Emit action only once per state visit. WAIT on subsequent calls without adding to history."""
        state_key = f"{state.value}@{self._state_entry_id}"
        if state_key not in self._action_emitted:
            self._action_emitted.add(state_key)
            return self._action(name, reason, current_time)
        return Wave1Action(name=Wave1ActionName.WAIT, reason="action_queued")

    def _transition_to(self, new_state: Wave1State, current_time: float) -> None:
        """Record state transition. Increments entry ID so one-shot fires on re-entry."""
        self._prev_state = self.state
        self.state = new_state
        self._state_entered_at = current_time
        self._state_entry_id += 1
        self._radiant_released_at = None

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
        self._stability.reset()
        self._action_emitted = set()
        self._compass_forced = False
        self._radiant_released_at = None
        self._state_entry_id = 0

    @property
    def stats(self) -> dict:
        return {
            "state": self.state.value,
            "prev_state": self._prev_state.value if self._prev_state else None,
            "radiant_kick_casts": self._radiant_kick_casts,
            "observation_scans": self._observation_scans,
            "cleanup_cycles": self._cleanup_cycles,
            "action_count": len(self._action_history),
        }
