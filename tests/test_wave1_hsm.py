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
        """HSM must wait damage_register_wait_ms AFTER release before VERIFY_COUNTER.
        With split states: CAST_CHARGED_RADIANT_KICK -> RELEASE_RADIANT_KICK -> WAIT -> VERIFY_COUNTER."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg

        hsm._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, 0.0)

        assert cfg.radiant_kick_charge_ms < cfg.damage_register_wait_ms

        action_at_charge_end = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
            current_time=2.0,
        )
        assert action_at_charge_end.name == Wave1ActionName.RELEASE_RADIANT_KICK
        assert hsm.state == Wave1State.RELEASE_RADIANT_KICK
        assert hsm._radiant_released_at == 2.0, \
            "_radiant_released_at should equal current_time after transition"

        action_during_wait = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
            current_time=2.5,
        )
        assert action_during_wait.name == Wave1ActionName.WAIT
        assert hsm.state == Wave1State.RELEASE_RADIANT_KICK

        action_after_wait = hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.9),
            compass=make_compass(),
            current_time=4.5,
        )
        wait_ms = cfg.damage_register_wait_ms
        assert wait_ms >= 2000, f"damage_register_wait_ms should be ~2200ms, got {wait_ms}ms"
        assert hsm.state == Wave1State.VERIFY_COUNTER
        assert action_after_wait.name == Wave1ActionName.READ_PROGRESS

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
        """An action should only be emitted once per state visit; re-entry can emit again."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        assert hsm.state == Wave1State.WAIT_PLAYER_CONTROL
        assert "WAIT_PLAYER_CONTROL@1" in hsm._action_emitted

        hsm._transition_to(Wave1State.CLEANUP_IF_NEEDED, tick())
        assert hsm.state == Wave1State.CLEANUP_IF_NEEDED

        a1 = hsm._emit_action_once(
            Wave1State.CLEANUP_IF_NEEDED,
            Wave1ActionName.CLEANUP_TARGET,
            "cleanup 1",
            tick(),
        )
        assert a1.name == Wave1ActionName.CLEANUP_TARGET
        assert "CLEANUP_IF_NEEDED@2" in hsm._action_emitted

        a2 = hsm._emit_action_once(
            Wave1State.CLEANUP_IF_NEEDED,
            Wave1ActionName.CLEANUP_TARGET,
            "cleanup 2",
            tick(),
        )
        assert a2.name == Wave1ActionName.WAIT, \
            "Second emit in same state visit should return WAIT"

        hsm._transition_to(Wave1State.CLEANUP_IF_NEEDED, tick())

        a3 = hsm._emit_action_once(
            Wave1State.CLEANUP_IF_NEEDED,
            Wave1ActionName.CLEANUP_TARGET,
            "cleanup after re-entry",
            tick(),
        )
        assert a3.name == Wave1ActionName.CLEANUP_TARGET, \
            "Re-entering state should emit action again"

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

    def test_reenter_cleanup_can_emit_again(self):
        """Re-entering CLEANUP_IF_NEEDED must emit CLEANUP_TARGET again."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.CLEANUP_IF_NEEDED, tick())

        a1 = hsm._emit_action_once(
            Wave1State.CLEANUP_IF_NEEDED, Wave1ActionName.CLEANUP_TARGET,
            "cleanup 1", tick(),
        )
        assert a1.name == Wave1ActionName.CLEANUP_TARGET

        a2 = hsm._emit_action_once(
            Wave1State.CLEANUP_IF_NEEDED, Wave1ActionName.CLEANUP_TARGET,
            "cleanup 2", tick(),
        )
        assert a2.name == Wave1ActionName.WAIT

        hsm._transition_to(Wave1State.CLEANUP_IF_NEEDED, tick())

        a3 = hsm._emit_action_once(
            Wave1State.CLEANUP_IF_NEEDED, Wave1ActionName.CLEANUP_TARGET,
            "cleanup after re-entry", tick(),
        )
        assert a3.name == Wave1ActionName.CLEANUP_TARGET, \
            "Re-entering CLEANUP_IF_NEEDED should emit action again"

    def test_geppo_does_not_advance_per_tick_without_elapsed(self):
        """Rapid ticks without elapsed time must NOT advance from AGGRO_WITH_GEPPO."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.AGGRO_WITH_GEPPO, tick())
        entry_time = tick()

        for i in range(10):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=0, confidence=0.9),
                compass=make_compass(),
                current_time=entry_time + 0.1,
            )

        assert hsm.state == Wave1State.AGGRO_WITH_GEPPO, \
            f"Rapid ticks should not advance geppo state; got {hsm.state}"
        assert hsm._radiant_kick_casts == 0, \
            "No radiant kick should be cast without aggro_wait elapsed"

        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.9),
            compass=make_compass(),
            current_time=entry_time + cfg.aggro_wait_ms / 1000.0 + 0.1,
        )
        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK

    def test_done_requires_forsaken_garden_transition(self):
        """DONE must require transition to The Forsaken Garden, not any stage change."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.CONFIRM_STAGE_TRANSITION, tick())
        hsm._prev_stage = "Shattered Ramparts"

        for _ in range(9):
            hsm.tick(
                game_state=None,
                progress=make_progress(
                    current=4, total=4, confidence=0.9,
                    stage_name="The Crimson Keep",
                ),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state == Wave1State.CONFIRM_STAGE_TRANSITION, \
            f"Wrong stage should not trigger DONE; got {hsm.state}"

        for _ in range(9):
            hsm.tick(
                game_state=None,
                progress=make_progress(
                    current=4, total=4, confidence=0.9,
                    stage_name="The Forsaken Garden",
                ),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state == Wave1State.DONE

    def test_guard_complete_rejects_greater_than_total(self):
        """guard_objective_complete must reject objective_current > objective_total."""
        from vcl_hsm.transitions import guard_objective_complete
        from vcl_core.schemas import ProgressState

        p_overflow = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=5,
            objective_total=4,
            confidence=0.9,
        )
        ok, reason = guard_objective_complete(p_overflow, min_confidence=0.65)
        assert not ok, f"Should reject overflow: {reason}"
        assert "overflow" in reason.lower()

        p_normal = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=4,
            objective_total=4,
            confidence=0.9,
        )
        ok2, _ = guard_objective_complete(p_normal, min_confidence=0.65)
        assert ok2

        p_none_total = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=4,
            objective_total=None,
            confidence=0.9,
        )
        ok3, reason3 = guard_objective_complete(p_none_total, min_confidence=0.65)
        assert not ok3
        assert "objective_total_not_set" in reason3

    def test_cast_emits_hold_then_release_then_wait_then_verify(self):
        """Normal CAST timeline: HOLD -> RELEASE -> WAIT (damage wait) -> VERIFY_COUNTER.
        Each action emits exactly once in its own state."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg
        charge_time = cfg.radiant_kick_charge_ms / 1000.0 + 0.05
        wait_time = cfg.damage_register_wait_ms / 1000.0 + 0.05

        hsm._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, 0.0)

        action_hold = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.9),
            compass=make_compass(),
            current_time=0.5,
        )
        assert action_hold.name == Wave1ActionName.HOLD_RADIANT_KICK
        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK

        action_release = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.9),
            compass=make_compass(),
            current_time=charge_time,
        )
        assert action_release.name == Wave1ActionName.RELEASE_RADIANT_KICK
        assert hsm.state == Wave1State.RELEASE_RADIANT_KICK

        action_wait = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.9),
            compass=make_compass(),
            current_time=charge_time + 1.0,
        )
        assert action_wait.name == Wave1ActionName.WAIT
        assert hsm.state == Wave1State.RELEASE_RADIANT_KICK

        action_verify = hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.9),
            compass=make_compass(),
            current_time=charge_time + wait_time,
        )
        assert action_verify.name == Wave1ActionName.READ_PROGRESS
        assert hsm.state == Wave1State.VERIFY_COUNTER

    def test_release_not_suppressed_by_one_shot(self):
        """RELEASE_RADIANT_KICK must NOT be suppressed after HOLD_RADIANT_KICK.
        With split states, they are in different state entries, so this cannot happen."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg

        hsm._transition_to(Wave1State.CAST_CHARGED_RADIANT_KICK, 0.0)

        action_hold = hsm._emit_action_once(
            Wave1State.CAST_CHARGED_RADIANT_KICK,
            Wave1ActionName.HOLD_RADIANT_KICK,
            "hold",
            0.5,
        )
        assert action_hold.name == Wave1ActionName.HOLD_RADIANT_KICK

        hsm._transition_to(Wave1State.RELEASE_RADIANT_KICK, 2.0)
        action_release = hsm._emit_action_once(
            Wave1State.RELEASE_RADIANT_KICK,
            Wave1ActionName.RELEASE_RADIANT_KICK,
            "release",
            2.05,
        )
        assert action_release.name == Wave1ActionName.RELEASE_RADIANT_KICK, \
            "RELEASE_RADIANT_KICK must emit in RELEASE_RADIANT_KICK state, not suppressed"

    def test_done_by_counter_reset_after_move_exit(self):
        """HSM must reach DONE when counter resets 0/4 after MOVE_TO_EXIT.
        This requires prev_objective==4 and confidence >= 0.75."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.CONFIRM_STAGE_TRANSITION, tick())
        hsm._prev_stage = "Shattered Ramparts"
        hsm._prev_objective = 4

        for _ in range(12):
            hsm.tick(
                game_state=None,
                progress=make_progress(
                    current=0, total=4, confidence=0.80,
                    stage_name="Shattered Ramparts",
                ),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state == Wave1State.DONE, \
            f"DONE expected from counter reset 0/4 with confidence>=0.75, got {hsm.state}"

    def test_no_done_by_counter_reset_before_move_exit(self):
        """Counter reset alone must NOT trigger DONE if prev_objective != 4.
        The guard checks prev_objective==4 as a prerequisite."""
        hsm = Wave1HSM()
        from vcl_hsm.transitions import guard_stage_transitioned

        progress = make_progress(current=0, total=4, confidence=0.80, stage_name="Shattered Ramparts")
        ok, reason = guard_stage_transitioned(
            prev_stage="Shattered Ramparts",
            prev_objective=2,
            progress=progress,
            expected_next_stage="The Forsaken Garden",
            timeout_sec=5.0,
            state_entered_at=0.0,
            current_time=1.0,
        )
        assert not ok, f"Counter reset with prev_objective=2 should not confirm transition: {reason}"
        assert "waiting_transition" in reason

    def test_low_confidence_does_not_consume_geppo_action(self):
        """Low-confidence frames in VERIFY_STAGE_UI must NOT consume GEPPO_STACK.
        HSM should use cfg.min_confidence (0.75) for stage_verified guard."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_STAGE_UI, tick())

        for _ in range(5):
            hsm.tick(
                game_state=None,
                progress=make_progress(
                    current=0, total=4, confidence=0.60,
                    stage_name="Shattered Ramparts",
                ),
                compass=make_compass(),
                current_time=tick(),
            )

        assert hsm.state == Wave1State.VERIFY_STAGE_UI, \
            f"Low confidence 0.60 < 0.75 must keep HSM in VERIFY_STAGE_UI, got {hsm.state}"
        assert any("VERIFY_STAGE_UI@" in k for k in hsm._action_emitted), \
            "VERIFY_STAGE_UI action should have been emitted at least once"

    def test_low_confidence_recovery_executes_action(self):
        """After low-confidence frames, once confidence >= min_confidence, HSM must emit."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.AGGRO_WITH_GEPPO, tick())
        entry_time = tick()

        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.60),
            compass=make_compass(),
            current_time=entry_time + 0.1,
        )
        assert hsm.state == Wave1State.AGGRO_WITH_GEPPO

        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, confidence=0.80),
            compass=make_compass(),
            current_time=entry_time + hsm.wave1_cfg.aggro_wait_ms / 1000.0 + 0.1,
        )
        assert hsm.state == Wave1State.CAST_CHARGED_RADIANT_KICK

    def test_simulate_objective_final_preserves_zero(self):
        """Simulate summary must report 0/4 as '0/4', not '?/4'.
        This tests the is-None guard pattern against the falsy-value bug."""
        from vcl_core.schemas import ProgressState

        final_progress = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=0,
            objective_total=4,
            confidence=0.85,
        )

        curr = final_progress.objective_current if final_progress.objective_current is not None else None
        total = final_progress.objective_total if final_progress.objective_total is not None else None
        if curr is not None and total is not None:
            objective_final = f"{curr}/{total}"
        elif curr is not None:
            objective_final = f"{curr}/?"
        else:
            objective_final = "?/?"

        assert objective_final == "0/4", \
            f"objective_current=0 should produce '0/4', got '{objective_final}'"
        assert objective_final != "?/4", "'0' must not be mistaken for None"

    def test_obs_haki_scan_early_exits_on_stable_4_4(self):
        """OBS_HAKI_SCAN must transition to ALIGN_TO_EXIT if stable 4/4 appears during scan."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        # Enter OBS_HAKI_SCAN at t=1.5 (after BOOT and one tick increment)
        hsm._transition_to(Wave1State.OBS_HAKI_SCAN, 1.5)

        # Feed stable 4/4 reads — not enough for stability window yet
        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=1.6,
        )
        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=1.7,
        )
        # Third read completes stability window (3 consecutive 4/4 with conf>=0.65)
        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=1.8,
        )

        assert hsm.state == Wave1State.ALIGN_TO_EXIT, \
            f"OBS_HAKI_SCAN should early-exit to ALIGN_TO_EXIT on stable 4/4, got {hsm.state}"

    def test_verify_counter_requires_window_before_obs_haki(self):
        """VERIFY_COUNTER must not transition to OBS_HAKI_SCAN before verification window expires."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_COUNTER, 0.0)

        # Feed incomplete counter immediately
        for i in range(10):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=3, total=4, confidence=0.8),
                compass=make_compass(),
                current_time=0.05 * i,
            )

        # Should still be verifying before window expires
        verify_window = cfg.verify_window_sec
        assert hsm.state == Wave1State.VERIFY_COUNTER, \
            f"VERIFY_COUNTER should still be active before {verify_window}s window expires"

    def test_verify_counter_goes_to_obs_after_window_with_incomplete(self):
        """VERIFY_COUNTER transitions to OBS_HAKI_SCAN after window expires and still incomplete."""
        hsm = Wave1HSM()
        cfg = hsm.wave1_cfg
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_COUNTER, 0.0)

        verify_window = cfg.verify_window_sec

        # Feed incomplete readings through the window
        for i in range(20):
            hsm.tick(
                game_state=None,
                progress=make_progress(current=3, total=4, confidence=0.8),
                compass=make_compass(),
                current_time=verify_window + 0.1 + i * 0.1,
            )

        assert hsm.state in (Wave1State.OBS_HAKI_SCAN, Wave1State.CLEANUP_IF_NEEDED), \
            f"VERIFY_COUNTER should transition to OBS_HAKI_SCAN after {verify_window}s window, got {hsm.state}"

    def test_verify_counter_stays_in_verify_on_impossible_drop(self):
        """VERIFY_COUNTER must not accept impossible counter reset (4/4 -> 0/4) during verify.

        Feed exactly 2 reads of 4/4 (not enough for stable_clear), then a 0/4 flicker.
        The impossible drop check should catch this and keep HSM in VERIFY_COUNTER.
        """
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_COUNTER, 0.0)

        # Only 2 reads of 4/4 (not enough for stability window of 3)
        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=0.0,
        )
        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=0.1,
        )

        # Flicker: 0/4 (impossible — enemies can't respawn mid-wave)
        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, total=4, confidence=0.8),
            compass=make_compass(),
            current_time=0.5,
        )

        # The impossible drop should be rejected, keeping HSM in VERIFY_COUNTER
        assert hsm.state == Wave1State.VERIFY_COUNTER, \
            f"VERIFY_COUNTER should not accept impossible 4/4 -> 0/4 drop, got {hsm.state}"

    def test_persistent_clear_requires_anchor_count(self):
        """is_persistent_clear must require at least 2 high-confidence anchors."""
        from vcl_hsm.stability import CounterStabilityTracker

        t = CounterStabilityTracker(
            persistent_window_size=12,
            persistent_required_total=8,
            persistent_required_strong=2,
            persistent_min_strong_confidence=0.75,
        )
        # 8 reads at 4/4 but 0 high-confidence anchors
        for _ in range(8):
            t.update(objective_current=4, objective_total=4, confidence=0.50)

        assert not t.is_persistent_clear(), (
            "is_persistent_clear should be False with 0 high-confidence anchors"
        )

    def test_persistent_clear_true_with_2_anchors(self):
        """is_persistent_clear returns True with >=8 reads at 4/4 and >=2 high-confidence anchors."""
        from vcl_hsm.stability import CounterStabilityTracker

        t = CounterStabilityTracker(
            persistent_window_size=12,
            persistent_required_total=8,
            persistent_required_strong=2,
            persistent_min_strong_confidence=0.75,
        )
        # 8 reads at 4/4, 2 with high confidence
        for i in range(8):
            conf = 0.80 if i < 2 else 0.50
            t.update(objective_current=4, objective_total=4, confidence=conf)

        assert t.is_persistent_clear(), (
            "is_persistent_clear should be True with 8 reads at 4/4 and 2 anchors"
        )

    def test_persistent_clear_false_without_enough_reads(self):
        """is_persistent_clear returns False when <8 total reads at 4/4."""
        from vcl_hsm.stability import CounterStabilityTracker

        t = CounterStabilityTracker(
            persistent_window_size=12,
            persistent_required_total=8,
            persistent_required_strong=2,
            persistent_min_strong_confidence=0.75,
        )
        # Only 5 reads at 4/4
        for i in range(5):
            conf = 0.80 if i < 2 else 0.50
            t.update(objective_current=4, objective_total=4, confidence=conf)

        assert not t.is_persistent_clear(), (
            "is_persistent_clear should be False with only 5 reads (< 8)"
        )

    def test_verify_counter_exits_on_persistent_clear(self):
        """VERIFY_COUNTER transitions to ALIGN_TO_EXIT when persistent 4/4 is confirmed."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_COUNTER, 0.0)
        hsm._stability.reset()

        # Feed enough reads to populate the persistent window: 8 at 4/4 with 2 high-confidence
        for i in range(8):
            conf = 0.80 if i < 2 else 0.50
            hsm.tick(
                game_state=None,
                progress=make_progress(current=4, total=4, confidence=conf),
                compass=make_compass(),
                current_time=0.1 * (i + 1),
            )

        assert hsm.state == Wave1State.ALIGN_TO_EXIT, \
            f"VERIFY_COUNTER should exit to ALIGN_TO_EXIT on persistent 4/4, got {hsm.state}"

    def test_verify_stage_ui_accepts_0_4_at_wave_start(self):
        """VERIFY_STAGE_UI must transition to AGGRO when initial counter is 0/4 with high confidence."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_STAGE_UI, tick())

        hsm.tick(
            game_state=None,
            progress=make_progress(current=0, total=4, confidence=0.85),
            compass=make_compass(),
            current_time=tick(),
        )

        assert hsm.state == Wave1State.AGGRO_WITH_GEPPO, \
            f"VERIFY_STAGE_UI should transition to AGGRO at 0/4, got {hsm.state}"

    def test_verify_stage_ui_accepts_4_4_at_wave_start(self):
        """VERIFY_STAGE_UI must transition to AGGRO when initial counter is 4/4 (resume mid-wave)."""
        hsm = Wave1HSM()
        tick = make_ticker()

        hsm.tick(game_state=None, progress=None, compass=None, current_time=tick())
        hsm._transition_to(Wave1State.VERIFY_STAGE_UI, tick())

        hsm.tick(
            game_state=None,
            progress=make_progress(current=4, total=4, confidence=0.85),
            compass=make_compass(),
            current_time=tick(),
        )

        assert hsm.state == Wave1State.AGGRO_WITH_GEPPO, \
            f"VERIFY_STAGE_UI should transition to AGGRO at 4/4 (resume mid-wave), got {hsm.state}"

    def test_guard_stage_verified_rejects_counter_too_high(self):
        """guard_stage_verified must reject objective_current in range [1, objective_total).
        Counter=0 (wave not started) and counter=objective_total (resume mid-wave) are valid."""
        from vcl_hsm.transitions import guard_stage_verified

        # Counter 1..total-1 should be rejected at wave start (impossible)
        p2 = make_progress(current=2, total=4, confidence=0.85)
        ok, reason = guard_stage_verified(p2)
        assert not ok, f"Should reject counter=2: {reason}"
        assert "initial_counter_too_high" in reason

        # Counter=0 should pass
        ok2, reason2 = guard_stage_verified(make_progress(current=0, total=4, confidence=0.85))
        assert ok2, f"Should accept counter=0: {reason2}"

        # Counter=4 (resume mid-wave) should pass
        ok3, reason3 = guard_stage_verified(make_progress(current=4, total=4, confidence=0.85))
        assert ok3, f"Should accept counter=4 (resume): {reason3}"

        # initial_counter_max=None disables the check
        ok4, reason4 = guard_stage_verified(make_progress(current=2, total=4, confidence=0.85), initial_counter_max=None)
        assert ok4, f"initial_counter_max=None should disable check: {reason4}"
