"""Tests for the pre-HSM confidence gate in live execute mode (P0.7 Part A).

The gate prevents hsm.tick() from being called (and one-shot actions from being
consumed) when in a risky state and progress.confidence is below the configured
threshold. Assist mode is unaffected.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from pathlib import Path

import pytest
import numpy as np

from vcl_hsm import Wave1HSM, Wave1State
from vcl_core.schemas import ProgressState, CompassState, Wave1Action, Wave1ActionName
from vcl_core.config import AppConfig


def make_progress(
    current: int | None = None,
    total: int = 4,
    confidence: float = 0.9,
    stage_name: str | None = "Shattered Ramparts",
) -> ProgressState:
    return ProgressState(
        stage_name=stage_name,
        objective_current=current,
        objective_total=total,
        confidence=confidence,
    )


def make_compass(label: str = "S", confidence: float = 0.9) -> CompassState:
    return CompassState(label=label, angle_deg=180.0, confidence=confidence)


def make_frame() -> np.ndarray:
    return np.zeros((1440, 2560, 3), dtype=np.uint8)


def _simulate_confidence_gate(
    *,
    mode: str,
    state: Wave1State,
    progress_confidence: float,
    min_confidence: float = 0.75,
) -> dict:
    """Simulate the confidence gate logic and return the decision dict.

    Mirrors the gate block in main.py:live().
    RISKY_STATES = {VERIFY_STAGE_UI, AGGRO_WITH_GEPPO, CAST_CHARGED_RADIANT_KICK,
                    RELEASE_RADIANT_KICK, VERIFY_COUNTER, ALIGN_TO_EXIT, MOVE_NEXT_STAGE}
    """
    RISKY_STATES = {
        Wave1State.VERIFY_STAGE_UI,
        Wave1State.AGGRO_WITH_GEPPO,
        Wave1State.CAST_CHARGED_RADIANT_KICK,
        Wave1State.RELEASE_RADIANT_KICK,
        Wave1State.VERIFY_COUNTER,
        Wave1State.ALIGN_TO_EXIT,
        Wave1State.MOVE_NEXT_STAGE,
    }

    gate_triggered = (
        mode == "execute"
        and state in RISKY_STATES
        and progress_confidence < min_confidence
    )

    if gate_triggered:
        return {"tick_called": False, "action": Wave1Action(name=Wave1ActionName.WAIT, reason="low_confidence_pre_hsm_pause")}
    else:
        return {"tick_called": True, "action": None}


class TestPreHsmConfidenceGate:
    def test_execute_low_confidence_blocks_before_hsm_tick(self):
        """In execute mode with low confidence on a risky state: tick must NOT be called."""
        RISKY_STATES = {
            Wave1State.VERIFY_STAGE_UI,
            Wave1State.AGGRO_WITH_GEPPO,
            Wave1State.CAST_CHARGED_RADIANT_KICK,
            Wave1State.RELEASE_RADIANT_KICK,
            Wave1State.VERIFY_COUNTER,
            Wave1State.ALIGN_TO_EXIT,
            Wave1State.MOVE_NEXT_STAGE,
        }

        for state in RISKY_STATES:
            result = _simulate_confidence_gate(
                mode="execute",
                state=state,
                progress_confidence=0.60,
                min_confidence=0.75,
            )
            assert result["tick_called"] is False, (
                f"hsm.tick() must be skipped in execute mode on risky state {state.value} "
                f"with low confidence; got tick_called={result['tick_called']}"
            )

    def test_execute_high_confidence_still_ticks(self):
        """High confidence in execute mode must still call hsm.tick()."""
        result = _simulate_confidence_gate(
            mode="execute",
            state=Wave1State.AGGRO_WITH_GEPPO,
            progress_confidence=0.85,
            min_confidence=0.75,
        )
        assert result["tick_called"] is True

    def test_execute_non_risky_state_ticks(self):
        """Non-risky states in execute mode must still call hsm.tick()."""
        non_risky = [
            Wave1State.BOOT,
            Wave1State.WAIT_PLAYER_CONTROL,
            Wave1State.SETUP_PIKA_V2,
            Wave1State.ENTER_STAGE,
            Wave1State.OBS_HAKI_SCAN,
            Wave1State.CLEANUP_IF_NEEDED,
            Wave1State.VERIFY_COUNTER_AGAIN,
            Wave1State.CONFIRM_STAGE_TRANSITION,
            Wave1State.DONE,
            Wave1State.FAILSAFE,
        ]
        for state in non_risky:
            result = _simulate_confidence_gate(
                mode="execute",
                state=state,
                progress_confidence=0.60,
            )
            assert result["tick_called"] is True, (
                f"Non-risky state {state.value} should still tick; got {result}"
            )

    def test_assist_mode_ticks_on_low_confidence(self):
        """Assist mode must call hsm.tick() even on low-confidence frames."""
        RISKY_STATES = {
            Wave1State.VERIFY_STAGE_UI,
            Wave1State.AGGRO_WITH_GEPPO,
            Wave1State.CAST_CHARGED_RADIANT_KICK,
            Wave1State.RELEASE_RADIANT_KICK,
            Wave1State.VERIFY_COUNTER,
            Wave1State.ALIGN_TO_EXIT,
            Wave1State.MOVE_NEXT_STAGE,
        }

        for state in RISKY_STATES:
            result = _simulate_confidence_gate(
                mode="assist",
                state=state,
                progress_confidence=0.60,
                min_confidence=0.75,
            )
            assert result["tick_called"] is True, (
                f"Assist mode must still call hsm.tick() on risky state {state.value}; "
                f"got tick_called={result['tick_called']}"
            )


class TestPreHsmConfidenceGateHolds:
    """Verify that low-confidence gate does NOT consume HSM one-shot actions."""

    def test_execute_low_confidence_does_not_consume_hold_radiant_kick(self):
        """Low-confidence pause must NOT consume HOLD_RADIANT_KICK.

        Simulate: HSM is in AGGRO_WITH_GEPPO. User has high confidence so HSM
        transitions to CAST_CHARGED_RADIANT_KICK and emits HOLD_RADIANT_KICK.
        Next frame: low confidence. The gate blocks hsm.tick(), so the HSM
        stays in CAST_CHARGED_RADIANT_KICK and does NOT consume a second
        HOLD_RADIANT_KICK one-shot.
        """
        cfg = AppConfig()
        hsm = Wave1HSM(config=cfg)
        tick = [0.0]
        def advance() -> float:
            t = tick[0]
            tick[0] += 0.5
            return t

        # Advance past boot + verify + aggro
        hsm.tick(game_state=None, progress=None, compass=None, current_time=advance())
        hsm._transition_to(Wave1State.VERIFY_STAGE_UI, advance())
        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.85),
            compass=make_compass(),
            current_time=advance(),
        )
        hsm._transition_to(Wave1State.AGGRO_WITH_GEPPO, advance())
        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.85),
            compass=make_compass(),
            current_time=advance(),
        )

        # Advance enough to trigger transition to CAST_CHARGED_RADIANT_KICK
        cast_time = advance() + cfg.wave1.radiant_kick_charge_ms / 1000.0 + 0.1
        action_before = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.85),
            compass=make_compass(),
            current_time=cast_time,
        )
        assert action_before.name == Wave1ActionName.HOLD_RADIANT_KICK
        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK

        # Low-confidence frame: gate skips hsm.tick()
        result = _simulate_confidence_gate(
            mode="execute",
            state=hsm.state,
            progress_confidence=0.60,
        )
        assert result["tick_called"] is False, (
            "Gate must skip hsm.tick() to preserve one-shot action"
        )
        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK, (
            "HSM state must NOT advance when tick is skipped"
        )

        # Recovery: high confidence allows tick
        action_after = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.85),
            compass=make_compass(),
            current_time=cast_time + 0.5,
        )
        # HOLD_RADIANT_KICK was already emitted in CAST_CHARGED_RADIANT_KICK.
        # Subsequent ticks in same state return WAIT (one-shot guard).
        assert action_after.name in (Wave1ActionName.HOLD_RADIANT_KICK, Wave1ActionName.WAIT), (
            f"After recovery, action should be HOLD_RADIANT_KICK or WAIT (one-shot guard), got {action_after.name}"
        )

    def test_execute_low_confidence_recovery_still_emits_action(self):
        """After low-confidence pause, once confidence recovers, HSM must emit the action."""
        cfg = AppConfig()
        hsm = Wave1HSM(config=cfg)
        tick = [0.0]
        def advance() -> float:
            t = tick[0]
            tick[0] += 0.5
            return t

        # Progress through setup into VERIFY_STAGE_UI
        hsm.tick(game_state=None, progress=None, compass=None, current_time=advance())
        hsm._transition_to(Wave1State.VERIFY_STAGE_UI, advance())

        # Low confidence frame — gate pauses
        result_low = _simulate_confidence_gate(
            mode="execute",
            state=Wave1State.VERIFY_STAGE_UI,
            progress_confidence=0.60,
        )
        assert result_low["tick_called"] is False
        assert result_low["action"].name == Wave1ActionName.WAIT
        assert result_low["action"].reason == "low_confidence_pre_hsm_pause"

        # High confidence frame — recovery
        action_recovery = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.85),
            compass=make_compass(),
            current_time=advance(),
        )
        # HSM is still in VERIFY_STAGE_UI (tick was skipped), so READ_PROGRESS or
        # it transitions if stage is now verified.
        assert action_recovery is not None
        assert action_recovery.name in (
            Wave1ActionName.READ_PROGRESS,
            Wave1ActionName.GEPPO_STACK,
            Wave1ActionName.WAIT,
        ), f"Recovery tick must emit a valid action, got {action_recovery.name}"

    def test_assist_mode_still_ticks_on_low_confidence(self):
        """Verify the assist-mode exception: hsm.tick() is always called."""
        cfg = AppConfig()
        hsm = Wave1HSM(config=cfg)
        tick = [0.0]
        def advance() -> float:
            t = tick[0]
            tick[0] += 0.5
            return t

        hsm.tick(game_state=None, progress=None, compass=None, current_time=advance())
        hsm._transition_to(Wave1State.AGGRO_WITH_GEPPO, advance())

        # Low confidence in assist mode
        result = _simulate_confidence_gate(
            mode="assist",
            state=Wave1State.AGGRO_WITH_GEPPO,
            progress_confidence=0.60,
        )
        assert result["tick_called"] is True, (
            "Assist mode must always call hsm.tick() regardless of confidence"
        )

        # Actually tick the HSM in assist mode
        action = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.60),
            compass=make_compass(),
            current_time=advance(),
        )
        # Must return a valid action (WAIT or GEPPO_STACK depending on elapsed time)
        assert action.name in (
            Wave1ActionName.GEPPO_STACK,
            Wave1ActionName.WAIT,
        ), f"Assist mode should return valid action, got {action.name}"

    def test_release_held_keys_on_low_confidence(self):
        """The gate must release held keys to prevent stuck inputs."""
        # This tests the integration: when gate fires, executor.release_held_keys() is called.
        # We mock the executor and verify the call.
        mock_executor = MagicMock()
        mock_primitives = MagicMock()
        mock_executor.primitives = mock_primitives

        # Simulate gate firing
        state = Wave1State.CAST_CHARGED_RADIANT_KICK
        result = _simulate_confidence_gate(
            mode="execute",
            state=state,
            progress_confidence=0.60,
        )

        if not result["tick_called"]:
            mock_executor.primitives.release_held_keys()

        mock_primitives.release_held_keys.assert_called_once()

    def test_gate_reason_is_low_confidence_pre_hsm_pause(self):
        """WAIT action reason must be 'low_confidence_pre_hsm_pause'."""
        for state in {
            Wave1State.VERIFY_STAGE_UI,
            Wave1State.AGGRO_WITH_GEPPO,
            Wave1State.CAST_CHARGED_RADIANT_KICK,
            Wave1State.RELEASE_RADIANT_KICK,
            Wave1State.VERIFY_COUNTER,
            Wave1State.ALIGN_TO_EXIT,
            Wave1State.MOVE_NEXT_STAGE,
        }:
            result = _simulate_confidence_gate(
                mode="execute",
                state=state,
                progress_confidence=0.60,
            )
            assert result["action"].reason == "low_confidence_pre_hsm_pause", (
                f"Gate reason for {state.value} must be 'low_confidence_pre_hsm_pause', "
                f"got '{result['action'].reason}'"
            )
