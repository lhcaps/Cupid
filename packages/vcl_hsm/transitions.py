"""HSM transition guard functions."""
from __future__ import annotations

from vcl_core.schemas import GameState, ProgressState, CompassState
from vcl_core.config import Wave1Config, SafetyConfig


def guard_can_exit(
    state: str,
    game_state: GameState | None,
    progress: ProgressState | None,
    safety_cfg: SafetyConfig,
    state_entered_at: float,
    current_time: float,
) -> tuple[bool, str]:
    """
    Universal exit guard: checks safety limits before any state transition.

    - Hard limit: always enforce max_state_duration_sec (prevents runaway states)
    - Confidence gate: only enforce once we are IN the wave loop (after VERIFY_STAGE_UI).
      During setup states, skip confidence gate so HSM can progress even with
      low/confidence counter readings from sparse video sampling.
    """
    elapsed = current_time - state_entered_at

    if elapsed > safety_cfg.max_state_duration_sec:
        return False, f"safety: max duration {safety_cfg.max_state_duration_sec}s exceeded"

    from vcl_hsm.states import WaveState
    wave_loop_states = (
        WaveState.AGGRO_WITH_GEPPO,
        WaveState.CAST_CHARGED_RADIANT_KICK,
        WaveState.RELEASE_RADIANT_KICK,
        WaveState.VERIFY_COUNTER,
        WaveState.OBS_HAKI_SCAN,
        WaveState.CLEANUP_IF_NEEDED,
        WaveState.VERIFY_COUNTER_AGAIN,
        WaveState.ALIGN_TO_EXIT,
        WaveState.MOVE_NEXT_STAGE,
        WaveState.CONFIRM_STAGE_TRANSITION,
    )

    if state in wave_loop_states:
        if progress is not None and progress.confidence > 0.0:
            if progress.confidence < 0.30:
                return False, f"low_confidence: {progress.confidence:.2f} < 0.30"

    return True, "ok"


def guard_wait_for_stage(
    progress: ProgressState | None,
    timeout_sec: float,
    entered_at: float,
    current_time: float,
) -> tuple[bool, str]:
    """GUARD for WAIT_PLAYER_CONTROL -> VERIFY_STAGE_UI."""
    if current_time - entered_at > timeout_sec:
        return False, f"stage_wait_timeout: {timeout_sec}s elapsed"
    if progress is not None and progress.stage_name is not None:
        return True, f"stage_detected: {progress.stage_name}"
    return False, "waiting_for_stage"


def guard_stage_verified(
    progress: ProgressState | None,
    expected_stage: str = "Shattered Ramparts",
    min_confidence: float = 0.75,
    initial_counter_max: int = 0,
    allow_resume_mid_wave: bool = False,
) -> tuple[bool, str]:
    """GUARD for VERIFY_STAGE_UI -> AGGRO_WITH_GEPPO.

    Args:
        progress: current progress state
        expected_stage: expected stage name
        min_confidence: minimum confidence for stage detection
        initial_counter_max: maximum acceptable objective_current for Wave 1 start.
            Defaults to 0 (Wave 1 must start at 0/4). Counter values in range
            1..objective_total-1 are "too high" and blocked unless allow_resume_mid_wave=True.
        allow_resume_mid_wave: if True, non-zero intermediate counters (1..total-1) are
            allowed through the guard with reason "mid_wave_resume_allowed". If False,
            they are blocked with "initial_counter_too_high".
    """
    if progress is None:
        return False, "no_progress_data"
    if progress.stage_name is None:
        return False, "stage_name_not_detected"
    if progress.objective_total != 4:
        return False, f"unexpected_objective_total: {progress.objective_total}"
    if progress.confidence < min_confidence:
        return False, f"low_stage_confidence: {progress.confidence:.2f} < {min_confidence}"
    stage_lower = progress.stage_name.lower().replace("'", "").replace(" ", "")
    expected_lower = expected_stage.lower().replace("'", "").replace(" ", "")
    if stage_lower != expected_lower:
        return False, f"wrong_stage: got {progress.stage_name}, expected {expected_stage}"

    # Initial counter check: reject impossible intermediate counters at wave start.
    # - Counter 0: valid (wave not started)
    # - Counter == objective_total: valid (mid-wave resume)
    # - Counter 1..objective_total-1: blocked unless allow_resume_mid_wave=True
    if (
        initial_counter_max is not None
        and progress.objective_current is not None
        and 1 <= progress.objective_current < (progress.objective_total or 4)
    ):
        if allow_resume_mid_wave:
            return True, f"mid_wave_resume_allowed: {progress.objective_current}/{progress.objective_total}"
        return False, f"initial_counter_too_high: {progress.objective_current}/{progress.objective_total}"

    return True, f"stage_verified: {progress.stage_name}"


def guard_geppo_done(
    geppo_count: int,
    config: Wave1Config,
    state_entered_at: float,
    current_time: float,
) -> tuple[bool, str]:
    """GUARD for AGGRO_WITH_GEPPO -> CAST_CHARGED_RADIANT_KICK.

    Geppo is considered done when:
    - Configured geppo count has been executed (caller is responsible for execution timing)
    - Aggro wait period has elapsed since entering AGGRO_WITH_GEPPO state
    """
    elapsed = current_time - state_entered_at
    if elapsed < config.aggro_wait_ms / 1000.0:
        return False, f"aggro_wait: {elapsed:.1f}s < {config.aggro_wait_ms}ms"
    return True, "ready_for_kick"


def guard_damage_registered(
    state_entered_at: float,
    config: Wave1Config,
    current_time: float,
) -> tuple[bool, str]:
    """GUARD for CAST_CHARGED_RADIANT_KICK -> VERIFY_COUNTER."""
    elapsed = current_time - state_entered_at
    wait = config.damage_register_wait_ms / 1000.0
    if elapsed < wait:
        return False, f"waiting_damage_register: {elapsed:.1f}s < {wait}s"
    return True, "damage_registered"


def guard_objective_complete(
    progress: ProgressState | None,
    min_confidence: float = 0.75,
) -> tuple[bool, str]:
    """GUARD for VERIFY_COUNTER -> ALIGN_TO_EXIT."""
    if progress is None:
        return False, "no_progress_data"
    if progress.objective_current is None:
        return False, "counter_not_read"
    if progress.objective_total is None:
        return False, "objective_total_not_set"
    if progress.objective_current > progress.objective_total:
        return False, f"overflow: {progress.objective_current}/{progress.objective_total}"
    if progress.objective_current < progress.objective_total:
        return False, f"incomplete: {progress.objective_current}/{progress.objective_total}"
    if progress.confidence < min_confidence:
        return False, f"low_confidence: {progress.confidence:.2f} < {min_confidence}"
    return True, f"complete: {progress.objective_current}/{progress.objective_total}"


def guard_objective_incomplete(
    progress: ProgressState | None,
) -> tuple[bool, str]:
    """GUARD for VERIFY_COUNTER -> OBS_HAKI_SCAN."""
    if progress is None:
        return False, "no_progress_data"
    if progress.objective_current is None:
        return False, "counter_not_read"
    if progress.objective_current >= (progress.objective_total or 4):
        return False, "objective_already_complete"
    return True, f"remaining: {progress.objective_current}/{progress.objective_total}"


def guard_compass_aligned(
    compass: CompassState | None,
    target_heading: str,
    tolerance_deg: int = 12,
    timeout_sec: float = 3.0,
    state_entered_at: float | None = None,
    current_time: float = 0.0,
) -> tuple[bool, str]:
    """GUARD for ALIGN_TO_EXIT -> MOVE_NEXT_STAGE."""
    if compass is None or compass.label is None:
        return False, "compass_not_read"
    if compass.confidence < 0.6:
        return False, f"low_compass_confidence: {compass.confidence:.2f}"

    from vcl_vision.compass_detector import HEADING_LABELS
    current = HEADING_LABELS.get(compass.label)
    target = HEADING_LABELS.get(target_heading)
    if current is None or target is None:
        return False, f"unknown_heading: {compass.label}"

    delta = abs(current - target)
    delta = min(delta, 360 - delta)

    if delta > tolerance_deg:
        return False, f"misaligned: {delta}deg > {tolerance_deg}deg tolerance"

    if state_entered_at is not None and current_time - state_entered_at > timeout_sec:
        return False, f"align_timeout: {timeout_sec}s exceeded"

    return True, f"aligned: {compass.label} (target {target_heading})"


def guard_stage_transitioned(
    prev_stage: str | None,
    prev_objective: int | None,
    progress: ProgressState | None,
    expected_next_stage: str = "The Forsaken Garden",
    timeout_sec: float = 5.0,
    state_entered_at: float = 0.0,
    current_time: float = 0.0,
) -> tuple[bool, str]:
    """GUARD for CONFIRM_STAGE_TRANSITION -> DONE.

    Requires explicit expected next stage.
    Fallback: counter reset (prev_objective==4 and current==0) only works after
    MOVE_TO_EXIT has been called, which is enforced by state machine flow.
    """
    if current_time - state_entered_at > timeout_sec:
        return False, "transition_timeout"

    if progress is None:
        return False, "no_progress_data_after_transition"

    expected_lower = expected_next_stage.lower().replace("'", "").replace(" ", "")
    current_lower = (progress.stage_name or "").lower().replace("'", "").replace(" ", "")

    if current_lower == expected_lower:
        return True, f"transition_confirmed: {progress.stage_name}"

    if (
        prev_stage is not None
        and prev_objective is not None
        and prev_objective == 4
        and progress.objective_current is not None
        and progress.objective_current == 0
        and progress.objective_total is not None
        and progress.objective_total == 4
        and progress.confidence >= 0.75
    ):
        return True, "transition_confirmed_by_counter_reset"

    return False, f"waiting_transition: stage={progress.stage_name}, expected={expected_next_stage}"
