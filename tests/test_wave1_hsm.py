"""Tests for Wave 1 HSM."""
from __future__ import annotations

import pytest
import time

from vcl_hsm import Wave1HSM, Wave1State
from vcl_core.schemas import ProgressState, CompassState, Wave1ActionName
from vcl_core.config import AppConfig


def make_progress(current: int | None = None, total: int = 4, confidence: float = 0.9) -> ProgressState:
    return ProgressState(
        stage_name="Shattered Ramparts",
        objective_current=current,
        objective_total=total,
        confidence=confidence,
    )


def make_compass(label: str = "S") -> CompassState:
    return CompassState(label=label, angle_deg=180, confidence=0.9)


class TestWave1HSM:
    def test_hsm_starts_at_boot(self):
        """HSM should start in BOOT state."""
        hsm = Wave1HSM()
        assert hsm.state == Wave1State.BOOT

    def test_boot_transitions_to_wait(self):
        """First tick should transition from BOOT to WAIT_PLAYER_CONTROL."""
        hsm = Wave1HSM()
        action = hsm.tick(game_state=None, progress=None, compass=None)
        assert hsm.state == Wave1State.WAIT_PLAYER_CONTROL
        assert action.name == Wave1ActionName.WAIT

    def test_hsm_never_exits_with_incomplete_objective(self):
        """HSM must NOT transition to ALIGN_TO_EXIT if counter < 4/4."""
        hsm = Wave1HSM()

        hsm.tick(game_state=None, progress=None, compass=None)
        hsm.tick(game_state=None, progress=make_progress(current=3, confidence=0.9), compass=None)
        hsm.tick(game_state=None, progress=make_progress(current=3, confidence=0.9), compass=None)

        assert hsm.state not in (Wave1State.ALIGN_TO_EXIT, Wave1State.MOVE_NEXT_STAGE, Wave1State.DONE)

    def test_hsm_blocks_4_4_with_low_confidence(self):
        """4/4 with confidence < 0.75 must NOT trigger exit."""
        hsm = Wave1HSM()

        for _ in range(20):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=4, total=4, confidence=0.6),
                compass=make_compass(),
            )

        assert hsm.state != Wave1State.DONE
        assert hsm.state != Wave1State.MOVE_NEXT_STAGE

    def test_hsm_completes_with_4_4_high_confidence(self):
        """4/4 with confidence >= 0.75 should reach ALIGN_TO_EXIT and progress."""
        hsm = Wave1HSM()
        t = [0.0]

        def tick_time() -> float:
            val = t[0]
            t[0] += 0.5
            return val

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick_time())

        hsm._geppo_count = 5
        hsm._transition_to(Wave1State.AGGRO_WITH_GEPPO, t[0])
        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(label="S"),
            current_time=tick_time(),
        )

        reached_exit_states = []
        for _ in range(30):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=4, total=4, confidence=0.9),
                compass=make_compass(label="S"),
                current_time=tick_time(),
            )
            if hsm.state in (
                Wave1State.ALIGN_TO_EXIT,
                Wave1State.MOVE_NEXT_STAGE,
                Wave1State.CONFIRM_STAGE_TRANSITION,
                Wave1State.DONE,
            ):
                reached_exit_states.append(hsm.state)

        assert Wave1State.ALIGN_TO_EXIT in reached_exit_states, (
            f"Expected HSM to reach ALIGN_TO_EXIT or beyond. "
            f"Got: {hsm.state.value}, reached: {[s.value for s in reached_exit_states]}"
        )

    def test_hsm_resets(self):
        """reset() should return HSM to BOOT."""
        hsm = Wave1HSM()
        hsm.tick(game_state=None, progress=None, compass=None)
        assert hsm.state != Wave1State.BOOT
        hsm.reset()
        assert hsm.state == Wave1State.BOOT

    def test_hsm_tracks_stats(self):
        """HSM stats should track radiant kicks and observation scans."""
        hsm = Wave1HSM()
        hsm.tick(game_state=None, progress=None, compass=None)
        stats = hsm.stats
        assert "state" in stats
        assert "radiant_kick_casts" in stats
        assert "observation_scans" in stats

    def test_hsm_guards_failsafe_on_timeout(self):
        """Long-running state should trigger failsafe."""
        hsm = Wave1HSM()
        hsm.tick(game_state=None, progress=None, compass=None)

        old_time = hsm._state_entered_at - 100.0
        hsm._state_entered_at = old_time

        action = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
        )
        assert action.name in (Wave1ActionName.STOP_FAILSAFE, Wave1ActionName.WAIT)

    def test_wave1state_is_terminal(self):
        """Only DONE and FAILSAFE should be terminal."""
        assert Wave1State.DONE.is_terminal is True
        assert Wave1State.FAILSAFE.is_terminal is True
        assert Wave1State.VERIFY_COUNTER.is_terminal is False
        assert Wave1State.ALIGN_TO_EXIT.is_terminal is False
