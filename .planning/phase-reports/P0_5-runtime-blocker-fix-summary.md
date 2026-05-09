# Phase P0.5 — Remaining Wave 1 Runtime Blockers Fix

**Date:** 2026-05-09
**Status:** COMPLETED
**All 9 fixes applied.** 46 unit tests pass (9 new tests added).

---

## What Changed

### Fix 1: Low-Confidence Execute Gate BEFORE executor.execute()
**File:** `apps/wave_runner/main.py`

The low-confidence gate previously ran AFTER `executor.execute()`, meaning the action was executed before keys were released on low confidence. Now the gate runs before `execute()`, releasing held keys and continuing without pressing anything when confidence is below threshold.

```python
# OLD order (WRONG):
executor.execute(action.name)        # pressed keys before gate check
if low_confidence: release_and_continue  # too late

# NEW order (CORRECT):
if low_confidence: release_and_continue  # gate before execute
executor.execute(action.name)
```

### Fix 2: release_held_keys() vs release_all_keys() Split
**File:** `packages/vcl_input/primitives.py`

- `release_held_keys()`: Releases all keys, clears `_held_keys`, but does NOT set `_stopped=True`. Used for temporary pauses (e.g., low-confidence) where execution may resume.
- `release_all_keys()`: Calls `release_held_keys()` then sets `_stopped=True`. Used for true emergency stop only.

Low-confidence pause now calls `release_held_keys()`, not `release_all_keys()`.

### Fix 3: ProgressDetector 0/4 Valid + Clamp Noise
**File:** `packages/vcl_vision/progress_detector.py`

- 0 filled circles with active wave panel now returns `confidence=0.70` (fixed from `confidence=0.0`) — enough for stage verification.
- Noise detecting more circles than `objective_total` is clamped: `filled_count = min(filled_count, cfg.objective_total)`.
- `test_progress_detector_zero_of_four_valid_confidence` and `test_progress_detector_clamps_noise_above_total` added.

### Fix 4: guard_objective_complete Rejects Overflow and None
**File:** `packages/vcl_hsm/transitions.py`

- Added check: `if progress.objective_current > progress.objective_total: return False, "overflow: ..."`
- Added check: `if progress.objective_total is None: return False, "objective_total_not_set"`
- `test_guard_complete_rejects_greater_than_total` added.

### Fix 5: Real Post-Release Damage Wait with _radiant_released_at
**File:** `packages/vcl_hsm/wave1_machine.py`

Previous bug: `RELEASE_RADIANT_KICK` was emitted only after the damage wait, meaning the release signal never actually went to the executor during the wait period.

New flow:
1. `HOLD_RADIANT_KICK` emitted while charging
2. At charge end (elapsed >= charge_ms): `RELEASE_RADIANT_KICK` emitted, `_radiant_released_at = current_time`
3. Subsequent ticks in same state: `WAIT` until `current_time - _radiant_released_at >= damage_register_wait_ms`
4. After damage wait: transition to `VERIFY_COUNTER`, emit `READ_PROGRESS`

Key: `_radiant_released_at` is reset to `None` in `_transition_to()`, and `_radiant_released_at = None` in `reset()`.

`test_damage_register_wait_prevents_immediate_verify` updated to verify RELEASE fires at charge end, then WAIT during damage wait, then VERIFY_COUNTER after wait.

### Fix 6: One-Shot by State Entry ID (Not Forever)
**File:** `packages/vcl_hsm/wave1_machine.py`

- Added `_state_entry_id: int` counter, incremented in `_transition_to()`
- `_emit_action_once` key changed from `state.value` to `f"{state.value}@{self._state_entry_id}"`
- Re-entering `CLEANUP_IF_NEEDED` or `OBS_HAKI_SCAN` increments entry ID, allowing action to emit again
- `_transition_to` resets `_radiant_released_at = None` on each transition
- `test_reenter_cleanup_can_emit_again` added.

### Fix 7: Geppo Not Tick-Driven
**File:** `packages/vcl_hsm/wave1_machine.py`

Previous bug: `_geppo_count += 1` on every HSM tick. With tick interval 0.5s and `geppo_count=5`, after 5 ticks (2.5s) the guard passed — even if `aggro_wait_ms=1000ms`.

Fix: Removed `_geppo_count` as a transition driver. `guard_geppo_done` now uses only elapsed time:
```python
elapsed = current_time - state_entered_at
if elapsed < config.aggro_wait_ms / 1000.0: return False
return True
```

`test_geppo_does_not_advance_per_tick_without_elapsed` added.

### Fix 8: Simulate Summary Truthfulness
**File:** `apps/wave_runner/main.py`

Previous bug: `status="clear"` and `objective_final="4/4"` were hardcoded.

Now:
- `status` = `"clear"` if `hsm.state == DONE`, else `"fail"`
- `objective_final` = `{hsm._prev_progress.objective_current}/{hsm._prev_progress.objective_total}` or `"?"` if no progress
- `failure_reason` = `None` if clear, else `hsm.state.value`

### Fix 9: DONE Requires Expected Next Stage
**Files:** `packages/vcl_hsm/transitions.py`, `packages/vcl_core/config.py`, `configs/*.yaml`

Previous bug: Any `stage_name != prev_stage` triggered DONE, meaning random stage names could cause false completion.

New guard: `guard_stage_transitioned` requires `progress.stage_name == expected_next_stage` (from config `wave1.next_stage_name = "The Forsaken Garden"`). Any other stage change is ignored.

`test_done_requires_forsaken_garden_transition` added.

### Config: next_stage_name Added
**Files:** `packages/vcl_core/config.py`, `configs/wave1.shattered_ramparts.yaml`, `configs/app.default.yaml`

Added `Wave1Config.next_stage_name: str = "The Forsaken Garden"` and aligned `radiant_kick_charge_ms=2000` in YAML configs.

---

## What Was Intentionally Not Changed

- No Wave 2+ implementation
- No full dungeon HSM
- No YOLO training
- No desktop UI polish
- Compass detector algorithm unchanged (helper-only, same as P0)
- `vcl_eval/metrics.py` and `vcl_eval/report.py` unchanged

---

## Verification Results

| Command | Result |
|---------|--------|
| `python tools/validate_install.py` | PASS |
| `pytest tests/` | **46 passed** (was 37 in P0, +9 new) |
| `python -m apps.replay_analyzer.main --help` | PASS |
| `python -m apps.wave_runner.main --help` | PASS |
| Replay smoke (MedalTV video, 159 frames) | PASS (conf 0.79-0.83) |
| HSM dry-run | PASS (final state FAILSAFE, correctly reported as "fail", objective_final="3/4") |

---

## Files Changed

| File | Change |
|------|--------|
| `packages/vcl_hsm/wave1_machine.py` | Fix 5 (damage wait), Fix 6 (entry ID), Fix 7 (geppo), emit RELEASE at charge end |
| `packages/vcl_hsm/transitions.py` | Fix 4 (overflow guard), Fix 9 (expected next stage) |
| `packages/vcl_input/primitives.py` | Fix 2 (release_held_keys vs release_all_keys) |
| `packages/vcl_input/executor.py` | Unchanged |
| `apps/wave_runner/main.py` | Fix 1 (gate order), Fix 8 (truthful summary) |
| `packages/vcl_core/config.py` | Fix 9 (next_stage_name field) |
| `packages/vcl_vision/progress_detector.py` | Fix 3 (0/4 conf, clamp noise) |
| `configs/wave1.shattered_ramparts.yaml` | Fix 9 (next_stage_name), radiant_kick_charge_ms=2000 |
| `configs/app.default.yaml` | Fix 9 (next_stage_name), radiant_kick_charge_ms=2000 |
| `tests/test_wave1_hsm.py` | 9 new tests + 2 updated for damage-wait flow |
| `tests/test_progress_detector.py` | 2 new tests (0/4 conf, clamp) |
| `tests/test_input_safety.py` | 3 new tests (release_held_keys semantics) |

---

## Known Remaining Live-Only Risks

1. **Counter detection on real gameplay**: Video frames show conf=0.79-0.83. Live screen capture may differ. Assist mode should be run first.
2. **Real damage registration timing**: The 2200ms wait is based on video analysis — real gameplay timing may vary. Live observe-and-tune may be needed.
3. **mss.mss() deprecation warning** in emergency_stop.py — low priority.
4. **Compass as helper**: Compass readings still fluctuate in video analysis — no fix applied per P0/P0.5 scope.

---

## Git

**Files to commit:** All changed files above + `.planning/ROADMAP.md` + `.planning/phase-reports/P0_5-runtime-blocker-fix-summary.md`
