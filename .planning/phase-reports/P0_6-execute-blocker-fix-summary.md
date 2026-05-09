# Phase P0.6: Fix Remaining Execute-Blocking HSM Bugs

**Commit:** `52a403e`
**Date:** 2026-05-09
**Status:** ✅ COMPLETE

---

## Summary

Fixed 5 execute-blocking bugs found during static review of Phase P0.5, making Wave 1 safe for live execution.

---

## Bug Fixes

### P0 Blocker 1 — CAST Action One-Shot Bug ✅

**Problem:** `HOLD_RADIANT_KICK` and `RELEASE_RADIANT_KICK` were emitted in the same `CAST_CHARGED_RADIANT_KICK` state entry. The one-shot mechanism keyed by `state@entry_id`, so after `HOLD` consumed the slot, `RELEASE` was suppressed. The executor held R but never received the release signal.

**Fix:** Split the monolithic `CAST_CHARGED_RADIANT_KICK` state into 3 explicit states:
- `CAST_CHARGED_RADIANT_KICK` — holds R until charge completes
- `RELEASE_RADIANT_KICK` — releases R, then waits for damage to register
- `VERIFY_COUNTER` — reads progress after damage window

`HOLD` and `RELEASE` are now in separate state entries, so each emits its one-shot action exactly once. `RELEASE_RADIANT_KICK` was also added to `wave_loop_states` in `guard_can_exit`.

**Files changed:** `packages/vcl_hsm/states.py`, `packages/vcl_hsm/wave1_machine.py`, `packages/vcl_hsm/transitions.py`

**Tests:** `test_cast_emits_hold_then_release_then_wait_then_verify`, `test_release_not_suppressed_by_one_shot`, `test_damage_register_wait_prevents_immediate_verify` (updated)

---

### P0 Blocker 2 — Impossible DONE Transition ✅

**Problem:** `ProgressDetector` always returns `stage_name = "Shattered Ramparts"` (from config). `guard_stage_transitioned` requires `"The Forsaken Garden"`. Since the detector has no stage OCR, DONE could never be reached in real execution.

**Fix:** Added a guarded counter-reset fallback in `guard_stage_transitioned`:
```
prev_objective == 4
AND current == 0 AND total == 4
AND confidence >= 0.75
→ transition confirmed by counter reset
```

This is safe because `_prev_objective` is only set after `ALIGN_TO_EXIT → MOVE_NEXT_STAGE` transition — meaning `MOVE_TO_EXIT` has already been called. The guard does not fire globally.

**Files changed:** `packages/vcl_hsm/transitions.py`

**Tests:** `test_done_by_counter_reset_after_move_exit`, `test_no_done_by_counter_reset_before_move_exit`

---

### P0 Blocker 3 — Low-Confidence Gate Consuming One-Shot Actions ✅

**Problem:** The live loop called `hsm.tick()` before the low-confidence gate. HSM could transition into an action state and consume a one-shot action (e.g., `GEPPO_STACK`), then the gate blocked execution. On the next tick, the action was already consumed and would not emit again.

**Fix (3 parts):**

1. **Threshold alignment:** `guard_stage_verified` now accepts `min_confidence` parameter (default `0.75`, matching `cfg.progress_ui.min_confidence`). `guard_objective_complete` default also raised from `0.65` to `0.75`. Both are called with `self.progress_cfg.min_confidence` from the HSM.

2. **Stability tracker:** `CounterStabilityTracker` now uses `cfg.min_confidence` instead of hardcoded `0.65`.

3. **Pre-gate in live loop:** For `RISKY_STATES` in `execute` mode, if `confidence < min_confidence`, the loop skips `hsm.tick()` entirely (just logs and continues). This prevents the one-shot mechanism from consuming actions on low-confidence frames. `RELEASE_RADIANT_KICK` was added to `RISKY_STATES`.

**Files changed:** `packages/vcl_hsm/transitions.py`, `packages/vcl_hsm/wave1_machine.py`, `apps/wave_runner/main.py`

**Tests:** `test_low_confidence_does_not_consume_geppo_action`, `test_low_confidence_recovery_executes_action`

---

### P1 Bug — `release_held_keys()` Incomplete Safety List ✅

**Problem:** `release_held_keys()` released `w/a/s/d/space/r/q/e/g/j` but not `"1"`, `"2"`, or the configured `slot_pika_v2`. Cleanup attack taps `"1"` and setup uses slot `"2"`.

**Fix:** Added `"1"`, `"2"`, and `self.keybinds.slot_pika_v2` to the `ALL_KEYS` list in `release_held_keys()`.

**Files changed:** `packages/vcl_input/primitives.py`

**Tests:** `test_release_held_keys_includes_slots_1_and_2`

---

### P1 Bug — `objective_final` Reports `?/4` When 0/4 ✅

**Problem:** The simulate summary used `objective_current or '?'` pattern. When `objective_current` is `0` (falsy), Python's `or` returns `'?'` instead of `0`.

**Fix:** Replaced all `or '?'` patterns with explicit `is None` checks in `apps/wave_runner/main.py`:
- Simulate `RunSummary.objective_final`
- Live loop `progress_str`
- Live loop `summary.objective_final`
- Logger `progress` string

**Files changed:** `apps/wave_runner/main.py`

**Tests:** `test_simulate_objective_final_preserves_zero`

---

## Test Results

```
54 tests passed (was 46 before P0.6)
  6 new tests added to test_wave1_hsm.py
  1 new test added to test_input_safety.py
  1 existing test updated (test_damage_register_wait_prevents_immediate_verify)
  2 assertions added to existing test (test_release_held_keys_allows_resume)
```

### New Tests
| Test | Covers |
|------|--------|
| `test_cast_emits_hold_then_release_then_wait_then_verify` | P0 Blocker 1: full HOLD→RELEASE→WAIT→VERIFY flow |
| `test_release_not_suppressed_by_one_shot` | P0 Blocker 1: RELEASE not consumed by HOLD |
| `test_done_by_counter_reset_after_move_exit` | P0 Blocker 2: DONE reachable via counter reset |
| `test_no_done_by_counter_reset_before_move_exit` | P0 Blocker 2: no DONE without prev_objective==4 |
| `test_low_confidence_does_not_consume_geppo_action` | P0 Blocker 3: no action consumed on low conf |
| `test_low_confidence_recovery_executes_action` | P0 Blocker 3: action emits when conf recovers |
| `test_release_held_keys_includes_slots_1_and_2` | P1 Bug: slots in safety list |
| `test_simulate_objective_final_preserves_zero` | P1 Bug: 0/4 reported as "0/4" |

### Test Fixes
- `test_damage_register_wait_prevents_immediate_verify`: Updated to verify `RELEASE_RADIANT_KICK` state and check `hsm._radiant_released_at` is set after transition.

---

## Verification Gates

| Gate | Status |
|------|--------|
| `pytest tests/` | ✅ 54/54 passed |
| `python tools/validate_install.py` | ✅ All checks passed |
| `python -m apps.replay_analyzer.main --help` | ✅ OK |
| `python -m apps.wave_runner.main --help` | ✅ OK |
| Replay smoke (wave1_001.mp4) | ⏭️ No replay video present |
| HSM dry-run on timeline | ⏭️ No timeline file present |

---

## Files Changed

| File | Change |
|------|--------|
| `packages/vcl_hsm/states.py` | +1 line: `RELEASE_RADIANT_KICK` state |
| `packages/vcl_hsm/wave1_machine.py` | Split CAST state, threshold alignment, stability tracker |
| `packages/vcl_hsm/transitions.py` | Counter-reset fallback, threshold params, `RELEASE_RADIANT_KICK` in wave_loop_states |
| `packages/vcl_input/primitives.py` | +3 keys to safety list |
| `apps/wave_runner/main.py` | Pre-gate, `is None` checks, `RELEASE_RADIANT_KICK` in RISKY_STATES |
| `tests/test_wave1_hsm.py` | +8 new tests, +1 updated test |
| `tests/test_input_safety.py` | +1 new test |

**Total:** 304 insertions, 34 deletions across 7 files.

---

## Git

```
commit 52a403e
fix: unblock wave1 execute safety flow
```
