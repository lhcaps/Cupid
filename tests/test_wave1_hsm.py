"""Tests for Wave 1 HSM — Wave 1 only, no multi-wave loop."""
from __future__ import annotations

import pytest

from vcl_hsm import Wave1HSM, Wave1State
from vcl_core.schemas import ProgressState, CompassState, Wave1ActionName
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
    angle_map = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
    return CompassState(label=label, angle_deg=angle_map.get(label, 180), confidence=confidence)


def make_ticker():
    """Simple time counter for HSM ticks."""
    t = [0.0]
    def tick() -> float:
        val = t[0]
        t[0] += 0.5
        return val
    return tick


class TestWave1HSM:
    def test_hsm_starts_at_boot(self):
        hsm = Wave1HSM()
        assert hsm.state == Wave1State.BOOT

    def test_boot_transitions_to_wait(self):
        hsm = Wave1HSM()
        action = hsm.tick(game_state=None, progress=None, compass=None)
        assert hsm.state == Wave1State.WAIT_PLAYER_CONTROL
        assert action.name == Wave1ActionName.WAIT

    def test_hsm_never_moves_to_exit_before_stable_4_4(self):
        """HSM must NOT reach ALIGN_TO_EXIT unless counter is 4/4 stable."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())

        for _ in range(10):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=3, confidence=0.9),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state not in (Wave1State.ALIGN_TO_EXIT, Wave1State.MOVE_NEXT_STAGE, Wave1State.DONE)

    def test_hsm_blocks_4_4_with_low_confidence(self):
        """4/4 with confidence < 0.75 must NOT reach exit states."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())

        for _ in range(30):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=4, total=4, confidence=0.6),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state != Wave1State.DONE
        assert hsm.state != Wave1State.MOVE_NEXT_STAGE

    def test_hsm_routes_3_4_to_haki_scan_not_exit(self):
        """Incomplete 3/4 must route to OBS_HAKI_SCAN or cleanup, not exit."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())

        hsm._transition_to(Wave1State.VERIFY_COUNTER, tick())
        for _ in range(5):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=3, confidence=0.9),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state in (Wave1State.OBS_HAKI_SCAN, Wave1State.CLEANUP_IF_NEEDED, Wave1State.VERIFY_COUNTER)
        assert hsm.state not in (Wave1State.ALIGN_TO_EXIT, Wave1State.MOVE_NEXT_STAGE, Wave1State.DONE)

    def test_hsm_reaches_done_after_transition_to_next_stage(self):
        """After stable 4/4 and stage transition, HSM must reach DONE."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())

        hsm._transition_to(Wave1State.CONFIRM_STAGE_TRANSITION, tick())
        hsm._prev_stage = "Shattered Ramparts"
        hsm._prev_objective = 4

        for _ in range(15):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=4, total=4, confidence=0.9, stage_name="The Forsaken Garden"),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state == Wave1State.DONE

    def test_hsm_does_not_loop_into_wave_2(self):
        """CONFIRM_STAGE_TRANSITION should reach DONE, not restart AGGRO."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())

        hsm._transition_to(Wave1State.CONFIRM_STAGE_TRANSITION, tick())
        hsm._prev_stage = "Shattered Ramparts"
        hsm._prev_objective = 4

        reached_states = []
        for _ in range(20):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=4, total=4, confidence=0.9, stage_name="The Forsaken Garden"),
                compass=make_compass(),
                current_time=tick(),
            )
            reached_states.append(hsm.state)

        assert Wave1State.DONE in reached_states
        assert Wave1State.AGGRO_WITH_GEPPO not in reached_states

    def test_damage_register_wait_prevents_immediate_verify(self):
        """HSM must wait damage_register_wait_ms before VERIFY_COUNTER after release."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg

        hsm._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, 0.0)
        hsm._state_entered_at = 0.0

        assert cfg.radiant_kick_charge_ms < cfg.damage_register_wait_ms

        action = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
            current_time=2.0,
        )

        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK
        assert action.name == Wave1ActionName.WAIT

        action2 = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
            current_time=3.9,
        )

        wait_ms = cfg.damage_register_wait_ms
        assert wait_ms >= 2000, f"damage_register_wait_ms should be ~2200ms, got {wait_ms}ms"
        assert hsm.state == Wave1State.VERIFY_COUNTER

    def test_hsm_resets(self):
        hsm = Wave1HSM()
        hsm.tick(game_state=None, progress=None, compass=None)
        assert hsm.state != Wave1State.BOOT
        hsm.reset()
        assert hsm.state == Wave1State.BOOT

    def test_hsm_tracks_stats(self):
        hsm = Wave1HSM()
        hsm.tick(game_state=None, progress=None, compass=None)
        stats = hsm.stats
        assert "state" in stats
        assert "radiant_kick_casts" in stats
        assert "observation_scans" in stats

    def test_hsm_guards_failsafe_on_timeout(self):
        hsm = Wave1HSM()
        hsm.tick(game_state=None, progress=None, compass=None)

        hsm._state_entered_at -= 100.0

        action = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
        )
        assert action.name in (Wave1ActionName.STOP_FAILSAFE, Wave1ActionName.WAIT)

    def test_wave1state_is_terminal(self):
        assert Wave1State.DONE.is_terminal is True
        assert Wave1State.FAILSAFE.is_terminal is True
        assert Wave1State.VERIFY_COUNTER.is_terminal is False
        assert Wave1State.ALIGN_TO_EXIT.is_terminal is False

    def test_action_is_one_shot(self):
        """An action should only be emitted once per state entry; subsequent ticks return WAIT."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        assert hsm.state == Wave1State.WAIT_PLAYER_CONTROL
        assert "WAIT_PLAYER_CONTROL" in hsm._action_emitted

        hsm._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, tick())
        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK

        t_charge = tick()
        hsm._emit_action_once(
            Wave1State.CAST_CHARGED_RADIANT_KICK,
            Wave1ActionName.HOLD_RADIANT_KICK,
            "charging",
            t_charge,
        )
        assert "CAST_CHARGED_RADIANT_KICK" in hsm._action_emitted

        emitted_actions = []
        for i in range(5):
            t_val = tick()
            a = hsm.tick(
                game_state=None,
                progress=make_progress(current=0, confidence=0.9),
                compass=make_compass(),
                current_time=t_val,
            )
            emitted_actions.append((i, t_val, a.name.value))

        assert emitted_actions[0][2] == "WAIT", f"First tick in CAST_CHARGED_RADIANT_KICK should WAIT (one-shot), got: {emitted_actions[0]}"
        wait_count = sum(1 for _, _, n in emitted_actions if n == "WAIT")
        assert wait_count == 3, f"Expected 3 WAIT ticks, got {wait_count}: {emitted_actions}"
        assert emitted_actions[3][2] == "RELEASE_RADIANT_KICK"
        assert emitted_actions[4][2] == "OBSERVATION_SCAN"

    def test_stable_4_4_required_for_exit(self):
        """Single 4/4 frame followed by unclear must NOT produce can_exit."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())

        hsm._transition_to(Wave1State.VERIFY_COUNTER, tick())

        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=tick(),
        )

        hsm.tick(
            game_state=None,
            progress=ProgressState(stage_name="Shattered Ramparts", confidence=0.0),
            compass=make_compass(),
            current_time=tick(),
        )

        assert hsm.state == Wave1State.VERIFY_COUNTER
