# P0.7 — Pre-HSM Confidence Gate + Region Calibration Tool

**Date:** 2026-05-09
**Status:** ✅ Complete

---

## Part A — Pre-HSM Confidence Gate

### Problem

`apps/wave_runner/main.py` called `hsm.tick()` before the low-confidence gate check
in the live execute loop. Since `Wave1HSM.tick()` calls `_emit_action_once()`, which
consumes one-shot actions (e.g., `HOLD_RADIANT_KICK`, `GEPPO_STACK`) when a state
is first entered, calling `tick()` on a low-confidence frame would silently advance
the HSM's internal state machine even though the executor was paused. This meant a
subsequent high-confidence frame would either see the HSM in an unexpected state or
fail to emit the intended one-shot action.

### Fix

The gate was already positioned **before** `hsm.tick()` in the loop — a prior
commit had introduced the correct structure. The only discrepancy was the
`WAIT` action reason string: it was `"low_confidence_paused"` but the spec
requires `"low_confidence_pre_hsm_pause"`.

**Change:** `apps/wave_runner/main.py`, line 231:
```python
# Before
action=Wave1Action(name=Wave1ActionName.WAIT, reason="low_confidence_paused")
# After
action=Wave1Action(name=Wave1ActionName.WAIT, reason="low_confidence_pre_hsm_pause")
```

### Behavior After Fix

- **Execute mode:** If `hsm.state in RISKY_STATES` and
  `progress.confidence < cfg.progress_ui.min_confidence` (0.75):
  - `executor.primitives.release_held_keys()` is called
  - `hsm.tick()` is **not called** — HSM state is frozen
  - `WAIT` with reason `"low_confidence_pre_hsm_pause"` is logged
  - `continue` skips the frame

- **Assist mode:** `hsm.tick()` is always called regardless of confidence.
  The user can observe HSM suggestions even on low-confidence frames.

- **Risky states:** `VERIFY_STAGE_UI`, `AGGRO_WITH_GEPPO`, `CAST_CHARGED_RADIANT_KICK`,
  `RELEASE_RADIANT_KICK`, `VERIFY_COUNTER`, `ALIGN_TO_EXIT`, `MOVE_NEXT_STAGE`

### Tests Added — `tests/test_confidence_gate.py`

| Test | Coverage |
|------|----------|
| `test_execute_low_confidence_blocks_before_hsm_tick` | All 7 risky states skip tick at confidence 0.60 < 0.75 |
| `test_execute_high_confidence_still_ticks` | High confidence (0.85) always ticks |
| `test_execute_non_risky_state_ticks` | Non-risky states always tick even on low conf |
| `test_assist_mode_ticks_on_low_confidence` | Assist mode always ticks (7 risky states) |
| `test_execute_low_confidence_does_not_consume_hold_radiant_kick` | Skip preserves one-shot; recovery emits correctly |
| `test_execute_low_confidence_recovery_still_emits_action` | Recovery emits valid action after pause |
| `test_assist_mode_still_ticks_on_low_confidence` | Confirms assist exception works |
| `test_release_held_keys_on_low_confidence` | Mock verifies `release_held_keys()` called on gate fire |
| `test_gate_reason_is_low_confidence_pre_hsm_pause` | Reason string matches spec on all risky states |

---

## Part B — Region Calibration Tool

### Tool: `tools/calibrate_regions.py`

Interactive OpenCV-based ROI calibration for live screen or static screenshots.

**Command:**
```bash
python tools/calibrate_regions.py --config configs/wave1.shattered_ramparts.yaml --out configs/wave1.local.yaml
python tools/calibrate_regions.py --image path/to/screenshot.png --config configs/wave1.shattered_ramparts.yaml --out out.yaml
```

### Features

1. **Live capture** via `mss` (monitor index configurable with `--monitor`)
2. **Static image mode** with `--image path/to/screenshot.png`
3. **4 ROI selections** via `cv2.selectROI` (rescaled 0.7x for usability):
   - `progress_ui.crop`
   - `progress_ui.counter_crop`
   - `progress_ui.wave_panel_crop`
   - `compass.crop`
4. **Conversion:** `cv2.selectROI` output (x, y, w, h) → [x1, y1, x2, y2]
5. **Validation:** Output path must differ from config path (no accidental mutation)
6. **Detection run:** `ProgressDetector` + `CompassDetector` run once on captured frame;
   results printed to stdout
7. **Debug overlay:** Saved to `reports/calibration/latest_overlay.jpg`
8. **YAML output:** Writes full config to `--out` with 4 updated crop regions;
   all other fields (screen, keybinds, wave1, safety, etc.) preserved

### Tests Added — `tests/test_calibrate_regions.py`

| Test | Coverage |
|------|----------|
| `test_roi_xywh_to_box_basic` | x,y,w,h → [x1,y1,x2,y2] correct |
| `test_roi_xywh_to_box_zero_dimensions` | Zero-dim ROI produces degenerate box |
| `test_roi_xywh_to_box_order` | x2 = x+w, y2 = y+h (handles negatives) |
| `test_box_to_crop_region_round_trip` | CropRegion → box → CropRegion preserves |
| `test_calibration_updates_yaml_structure` | All 4 crops written correctly |
| `test_calibration_preserves_unrelated_config_fields` | screen/keybinds/wave1/safety unchanged |
| `test_updated_yaml_round_trip` | yaml.dump → load → values match |
| `test_update_config_with_rois_returns_dict` | Returns plain dict for yaml.dump |

---

## Verification Results

| Check | Result |
|-------|--------|
| `python tools/validate_install.py` | ✅ All dependencies + packages OK |
| `python -m apps.wave_runner.main --help` | ✅ 4 commands: simulate, live, report, keyboard-test |
| `python tools/calibrate_regions.py --help` | ✅ --config, --out, --image, --monitor |
| `pytest tests/ -v` | ✅ **71/71 passed** (0.42s) |

---

## Files Changed

| File | Change |
|------|--------|
| `apps/wave_runner/main.py` | Fix WAIT reason string to `low_confidence_pre_hsm_pause` |
| `tests/test_confidence_gate.py` | **New** — 9 tests for Part A |
| `tests/test_calibrate_regions.py` | **New** — 8 tests for Part B |
| `tools/calibrate_regions.py` | **New** — Region calibration tool |
| `.planning/phase-reports/P0_7-confidence-gate-and-calibration-summary.md` | **New** — This report |
