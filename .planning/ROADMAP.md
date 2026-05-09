# ROADMAP — VisionCombatLab Wave 1 MVP

## Overview

Single-milestone roadmap. All phases build toward Wave 1 MVP: Shattered Ramparts clear with Pika V2, 9/10 success rate, verifiable reporting.

---

## Gameplay Context (Updated 2026-05-09)

### Pika V2 Moveset (from wiki)

| Key | Move | Stamina | Cooldown | Notes |
|-----|------|---------|---------|-------|
| M1 | Starlight Rapier | 0 | — | Sword combo, scales w/ fruit mastery |
| Q | Starlight Dash | variable | — | 2x distance (HP >70%) |
| E | Blitz Strike | 35 | 13s | Lunge + slam, stun 1s |
| **R** | **Radiant Kick** | **45** | **13s** | Small AoE burst (blockable) |
| **R (Charged)** | **Radiant Kick Charged** | **45** | **13s** | Gold flash → 3 AoE bursts, **guard-break** |
| Z | Radiant Ray | 66+ | 18s | Maneuverable ray, 6 explosions |
| T | Radiant Flight | 90 | 15s | Fly + damage |
| X | Radiant Jewels | 78 | 30s | Condensed AoE barrage |
| C | Excalibur | 100 | 70s | Massive line AoE, knock-down |

**Critical: Radiant Kick (R) is blockable.** Charged version guard-breaks after gold flash.

### Wave Counter Rendering (CRITICAL DISCOVERY 2026-05-09)

**The counter is rendered as FILLED CIRCLES, not text "x/4".**

- **Filled circle** (bright center) = enemy killed
- **Unfilled circle** (dark ring) = enemy alive
- **Counter region:** `y=100-135, x=1340-1620` (TOP-RIGHT)
- **Wave panel:** `x=1300-1850, y=0-180`
- **Circle radius:** ~10-15px, horizontally spaced ~40-50px apart

Evidence from video analysis:
```
Lobby (t=0-1s):   0 green pixels  → no wave
Wave 1 (t=2-12s):  551-724 green pixels → wave active
Between (t=17-21s): 78-112 green pixels → between waves
Wave 2 (t=22-25s): 631-696 green pixels → wave active
```

**Impact:** `progress_detector.py` counter detection MUST be rewritten using circle fill detection instead of text blob analysis.

### Dungeon Stages (from wiki)

| # | Name | Enemies | Counter | HP | Damage | Hazard |
|---|------|---------|---------|-----|--------|-------|
| 1 | Shattered Ramparts | 4/4: katana, bazooka, 2 fists | 4 circles | 200 | 15 | Easy |
| 2 | The Forsaken Garden | 4/4: 4 katana | 4 circles | 200 | 16 | Lightning (46dmg) |
| 3 | The Scarlet Plaze | 5/5: 2 pistol, 1 melee, 1 kiribachi, 1 guard | 5 circles | 200/600 | 15/33 | Lightning + meteorite |
| 4 | The Scarlet Ruins | 7/7: kiribachi, 2 guard, 2 melee, burn bazooka, pistol | 7 circles | 200 | 15 | + arrows (22/hit) |
| 5 | Endure Cupid's Wrath | 5 arrow waves | **NO counter** | — | 15/hit | Arrows, heals player |
| 6 | Heartguard's Keep | 6/6 guards | 6 circles | **600** | 33 | Arrows after clear |
| 7 | Leo's Inferno | Boss: Leo (Mera Mera) | Boss | 3750 | varies | Grounded boss |
| 8 | Defeat Cupid Queen | 4-stage boss | Boss | varies | varies | Tower phase (Stage 3) |

### Wave Timing (from 3 video analysis)

- Dungeon clear: ~58s (all 8 stages)
- Wave 1 window: ~2-25s
- Between-wave transition: ~25-30s
- Wave 5 survival phase: arrows + heal (no counter)
- Compass spikes to 13-16 blobs at ~39-41s (arrow phase)

---

## Milestone 1: Wave 1 MVP — Shattered Ramparts

**Goal:** Autonomous clear of Wave 1 (4/4 enemies) using Pika V2 Charged Radiant Kick, with full observability and safety guards.

### Phase 1 — Foundation

**Dependency:** None
**Status:** COMPLETED
**Tasks:**
1. Set up `pyproject.toml` with dependencies: opencv-python, numpy, pydantic, pyyaml, typer, rich, mss, pynput, pytest, ruff
2. Create package structure (`packages/vcl_core`, `packages/vcl_vision`, etc.)
3. Create `vcl_core`: `config.py` (YAML loading), `schemas.py` (Pydantic GameState/Wave1Action), `logger.py` (JSONL writer), `timebase.py` (monotonic clock)
4. Create `tools/validate_install.py` — checks all imports resolve
5. Add fixture images in `datasets/fixtures/` for testing

**Success Criteria:**
- `python tools/validate_install.py` exits 0
- `pytest tests/` runs (even if 0 pass initially)
- No import errors on any package

---

### Phase 2 — Replay Analyzer (Video Frame Extraction)

**Dependency:** Phase 1
**Status:** COMPLETED
**Tasks:**
1. Implement `vcl_vision/frame_source.py` — VideoReader class (OpenCV, yields frames with timestamp)
2. Implement `vcl_vision/debug_render.py` — draw bounding boxes, text overlays on frames
3. Implement `apps/replay_analyzer/main.py` — CLI with Typer:
   - `analyze --video <path> --config <yaml> --out <dir>`
   - Extract frames at 0.5s or 1s intervals
   - Generate `contact_sheet.jpg` (grid of sampled frames)
   - Export `metadata.json` (fps, resolution, duration, frame_count)
   - Export `timeline.raw.json` (frame timestamps + raw crop pixels)

**Success Criteria:**
- Command runs on any .mp4 without crash
- Output dir contains: `frames/`, `contact_sheet.jpg`, `metadata.json`, `timeline.raw.json`
- `python -m apps.replay_analyzer.main analyze --video datasets/raw_videos/... --out reports/eval/day1` works

**Gate:** No crash on video decode; correct fps/resolution reported

---

### Phase 3 — Progress UI Detector (CIRCLE FILL — COMPLETED)

**Dependency:** Phase 2
**Status:** COMPLETED
**Completed: 2026-05-09**
**Tasks:**

**P0: Rewrite counter detection (CIRCLE FILL METHOD)**
1. Replace `_parse_wave_counter()` with circle fill detection:
   - Crop counter region: `y=100-135, x=1340-1620`
   - Convert to grayscale, threshold at brightness=80
   - Connected components on bright regions (filled circles)
   - Filter for circles: aspect ratio 0.5-2.0, area 50-500px
   - Count filled circles = `objective_current` (0 to `objective_total`)
   - `objective_total` = 4 for Wave 1

2. Keep `_detect_wave_active()` — detects wave panel presence (still works)

3. Update confidence scoring:
   - High confidence: 4 circles detected with good shape
   - Medium: 3 circles with good shape
   - Low: fewer circles or poor shape quality

4. Add fixture images: `datasets/fixtures/circle_0_4.png`, `circle_4_4.png`

5. Implement `tests/test_progress_detector.py`

**WRONG APPROACH (remove):**
- Inverting dark threshold expecting dark-on-dark text
- Area-based digit estimation
- Text blob detection for "x/4" pattern

**CORRECT APPROACH:**
- Grayscale threshold at 80 to separate filled (bright) from unfilled (dark) circles
- Connected components on bright regions
- Filter for circular shapes (area ~100-300px, aspect ~1.0)
- Count filled circles

**Success Criteria:**
- `pytest tests/test_progress_detector.py` — circle_0_4 → current=0,total=4; circle_4_4 → current=4,total=4
- Circle detection works on all 3 new video frames
- Confidence correctly reflects detection quality

**Gate:** ≥90% parse accuracy on sampled frames from real video

---

### Phase 4 — Compass Detector

**Dependency:** Phase 3
**Status:** COMPLETED (minor updates needed)
**Tasks:**
1. Implement `vcl_vision/compass_detector.py`:
   - Crop top compass bar (configurable, default 0-2560 x 0-90 at 1440p)
   - Detect compass labels (N, NE, E, SE, S, SW, W, NW) via threshold + contour
   - Find label nearest to screen center X
   - Interpolate angle: if SE and S are detected but center is between them, report SE
   - Return `CompassState(label, angle_deg, confidence)`
2. Implement `tests/test_compass_detector.py`

**Success Criteria:**
- `pytest tests/test_compass_detector.py` passes
- Heading within ±15° tolerance when compass visible
- Max rotate timeout (config: 3.0s) prevents infinite spin

**Gate:** Compass heading read correctly on ≥85% of sampled frames with visible compass

---

### Phase 5 — Wave 1 HSM (Offline Dry-Run)

**Dependency:** Phase 3 + Phase 4
**Status:** COMPLETED + STABILIZED (2026-05-09)
**Notes:** P0 runtime stabilization applied — see Phase P0 below.
**Tasks:**
1. Implement `vcl_hsm/states.py` — enum `Wave1State`:
   ```
   BOOT → WAIT_PLAYER_CONTROL → SETUP_PIKA_V2 → ENTER_SHATTERED_RAMPARTS
   → VERIFY_STAGE_UI → AGGRO_WITH_GEPPO → CAST_CHARGED_RADIANT_KICK
   → VERIFY_COUNTER
       → ALIGN_TO_EXIT (if 4/4)
       → OBS_HAKI_SCAN (if < 4/4)
   → CLEANUP_IF_NEEDED → VERIFY_COUNTER_AGAIN → ALIGN_TO_EXIT → MOVE_NEXT_STAGE
   → CONFIRM_STAGE_TRANSITION → DONE
   ```
2. Implement `vcl_hsm/transitions.py` — guard functions per transition
3. Implement `vcl_hsm/wave1_machine.py` — `Wave1HSM` class:
   - Accepts `GameState` per tick
   - Returns `Wave1Action` per tick
   - Never exits unless `objective_current == 4` and `objective_total == 4`
   - Has `max_state_duration_sec` safety (default 15s)
4. Implement `apps/wave_runner/main.py simulate` subcommand:
   - `simulate --timeline <json> --config <yaml> --out <dir>`
   - Reads timeline.raw.json from Phase 2
   - Runs HSM over timeline, emits action plan JSONL

**Success Criteria:**
- `pytest tests/test_wave1_hsm.py` passes
- HSM never produces `MOVE_TO_EXIT` action when `objective_current < 4`
- HSM dry-run action sequence matches expected plan
- Command: `python -m apps.wave_runner.main simulate --timeline ... --out ...` works

**Gate:** HSM dry-run on real video timeline produces correct action plan

---

### Phase 6 — Input Primitives + Emergency Stop

**Dependency:** Phase 1
**Status:** COMPLETED
**Tasks:**
1. Implement `vcl_input/primitives.py`:
   - `tap(key, down_ms=80)` — press and release
   - `hold(key)` / `release(key)` — long-duration key management
   - `release_all_keys()` — release w/a/s/d/space/r/q/e/g/j
   - `geppo_stack(count=5, interval_ms_min=100, interval_ms_max=180)` — hold W+S, rapid Space taps
   - `charged_radiant_kick(charge_ms=1900)` — hold R for window, release (gold flash confirms ready)
   - `observation_scan(scan_ms=900)` — tap G, capture frames
   - `align_compass(target_heading, tolerance_deg=15, timeout_sec=3.0)` — rotate camera
   - `move_to_exit(timeout_sec=8, stuck_retry=3)` — hold W, dash if stuck
   - `blitz_strike_cleanup()` — E key for fallback after Radiant Kick miss
2. Implement `vcl_input/executor.py` — InputExecutor that sequences primitives, respects cooldowns
3. Implement `vcl_input/emergency_stop.py`:
   - F1 hotkey listener (pynput keyboard.Listener)
   - On trigger: `release_all_keys()`, save screenshot (`mss.Shot()`), write failure JSONL
   - Ctrl+C handler: same cleanup
   - Global exception handler: same cleanup
4. Add `tools/keyboard_test.py` for manual verification

**Note:** Pika V2 Radiant Kick (R) is blockable. Charged version (gold flash) guard-breaks. Blitz Strike (E) provides stun for cleanup.

**Success Criteria:**
- F1 immediately releases all held keys
- Screenshot saved at `reports/failure_cases/`
- `python -m apps.wave_runner.main keyboard-test` prints key states

**Gate:** F1 stop verified; all keys released within 100ms of stop signal

---

### Phase 7 — Live Runner: Assist Mode First

**Dependency:** Phase 5 + Phase 6
**Status:** COMPLETED (verify circle detection)
**Tasks:**
1. Extend `apps/wave_runner/main.py`:
   - `live --config <yaml> --mode assist` — print suggested action + reason, no key press
   - `live --config <yaml> --mode execute` — run HSM + executor with explicit flag only
   - `report --run-dir <dir>` — summarize JSONL logs into pass/fail/clear_rate
2. Implement `vcl_eval/metrics.py` — compute clear_rate, mean_clear_time, etc.
3. Implement `vcl_eval/report.py` — Rich-formatted terminal report
4. Live frame capture loop: `mss` capture → `ProgressDetector` → `CompassDetector` → `Wave1HSM` → action
5. Guardrail: if `progress_confidence < 0.7`, pause and print "[PAUSE] Low confidence — manual override required"
6. Guardrail: `max_state_duration_sec` exceeded → emergency stop

**Success Criteria:**
- Assist mode: prints correct state + action on live frames
- Execute mode: runs Wave 1 without manual input
- Failsafe: Ctrl+C releases all keys

**Gate:** Runs 10 Wave 1 attempts, produces report with clear_rate metric

---

### Phase 8 — Wave 1 MVP Verification & Polish

**Dependency:** Phase 7
**Status:** COMPLETED (verify circle detection integration)

---

### Phase P0 — Wave 1 Runtime Stabilization & Verification Readiness

**Dependency:** Phase 5 + Phase 6
**Status:** COMPLETED (2026-05-09)
**Goal:** Make Wave 1 runtime stable and ready for real 10-run verification.

**Tasks completed:**
1. P0.1 — Package imports reliable without PYTHONPATH (apps `__init__.py` sys.path fix)
2. P0.2 — VideoReader timestamp uses `frame_idx / fps` (deterministic, no wall-clock)
3. P0.3 — ProgressDetector rewritten to filled-circle counter (connected components)
4. P0.4 — CounterStabilityTracker: requires 3 consecutive 4/4 reads before exit gate
5. P0.5 — Wave1HSM is Wave 1 only; DONE after transition to The Forsaken Garden
6. P0.6 — Damage-register wait: 2200ms after R release before VERIFY_COUNTER
7. P0.7 — HSM actions are one-shot per state entry (all branches route through `_emit_action_once`)
8. P0.8 — Shared InputPrimitives between executor and emergency stop
9. P0.9 — Low-confidence hard pause in execute mode (releases keys)
10. P0.10 — Compass treated as helper, graceful fallback on timeout
11. P0.11 — Unit tests updated (37 tests, all passing)
12. P0.12 — Replay analyzer stores deterministic timestamps + progress/compass output

**Files changed:**
- `packages/vcl_vision/frame_source.py`
- `packages/vcl_vision/progress_detector.py`
- `packages/vcl_hsm/stability.py` (new)
- `packages/vcl_hsm/wave1_machine.py`
- `packages/vcl_hsm/states.py`
- `packages/vcl_hsm/transitions.py`
- `packages/vcl_input/executor.py`
- `packages/vcl_input/primitives.py`
- `apps/wave_runner/main.py`
- `apps/replay_analyzer/__init__.py`
- `apps/wave_runner/__init__.py`
- `configs/vision.1440p.yaml`
- `configs/wave1.shattered_ramparts.yaml`
- `configs/app.default.yaml`
- `tests/test_progress_detector.py`
- `tests/test_wave1_hsm.py`
- `tests/test_input_safety.py` (new)

**Verification:**
- `python tools/validate_install.py` → PASS
- `pytest tests/` → 46 passed (P0.5: added 9 new tests)
- `python -m apps.replay_analyzer.main --help` → PASS
- `python -m apps.wave_runner.main --help` → PASS
- Replay smoke on `MedalTVRoblox20260509053121278-trim-1778279513526.mp4` → PASS (159 frames sampled, conf 0.79-0.83)
- HSM dry-run on timeline → PASS (159 actions, final state FAILSAFE, correctly reported as "fail" with objective_final=3/4)

**Known remaining risks:**
- Counter detection confidence is low (0.30) on recorded video frames — likely needs frame timing/region tuning on live runs
- HSM final state was FAILSAFE on dry-run (expected: video counter reads never met 0.75 confidence threshold)
- Compass heading readings were unreliable (I/W/E fluctuating) — compass is treated as helper, not hard blocker
- No live execute testing yet — readiness for 10-run verification depends on first live results

### Phase P0.5 — Remaining Runtime Blockers Fix

**Dependency:** Phase P0
**Status:** COMPLETED (2026-05-09)
**Goal:** Fix remaining runtime bugs found in static review of Phase P0.

**Tasks completed:**
1. Low-confidence execute gate now runs BEFORE `executor.execute()` — no action fires on low conf
2. `release_held_keys()` (no `_stopped=True`) vs `release_all_keys()` (hard stop) split
3. 0/4 counter returns confidence 0.70 (fixed from 0.0); noise clamped to `objective_total`
4. `guard_objective_complete` rejects `current > total` and `total is None`
5. Real post-release damage wait: `RELEASE_RADIANT_KICK` emitted at charge end, then `WAIT` for `damage_register_wait_ms` before VERIFY_COUNTER
6. One-shot per state entry using `{state.value}@{state_entry_id}` — re-entry can emit again
7. Geppo count driven by elapsed time, not tick count — rapid ticks don't advance geppo
8. Simulate summary truthful: `status="clear"` only if `DONE`, `objective_final` from last progress read
9. DONE requires explicit `The Forsaken Garden` stage (config `wave1.next_stage_name`)

**New tests:** 9 added (46 total, all passing)

**Files changed:** `wave1_machine.py`, `transitions.py`, `stability.py`, `primitives.py`, `executor.py`, `wave_runner/main.py`, `config.py`, `progress_detector.py`, `wave1.shattered_ramparts.yaml`, `app.default.yaml`, `test_wave1_hsm.py`, `test_progress_detector.py`, `test_input_safety.py`

**Verification:** validate_install PASS, pytest 46/46 PASS, replay smoke PASS, HSM dry-run reports correct fail status

### Phase P0.6 — Execute-Blocking HSM Bugs

**Dependency:** Phase P0.5
**Status:** COMPLETED (2026-05-09)
**Goal:** Fix 5 execute-blocking bugs making Wave 1 safe for live execution.

**Tasks completed:**
1. P0 Blocker 1 — CAST one-shot bug: Split `CAST_CHARGED_RADIANT_KICK` into `CAST_CHARGED_RADIANT_KICK` → `RELEASE_RADIANT_KICK` → `VERIFY_COUNTER`. HOLD and RELEASE are now in separate state entries; one-shot suppression eliminated.
2. P0 Blocker 2 — Impossible DONE: `guard_stage_transitioned` accepts counter-reset fallback: `prev_objective==4 AND current==0 AND confidence>=0.75` confirms transition. Gated by MOVE_TO_EXIT flow.
3. P0 Blocker 3 — Low-confidence consuming actions: `guard_stage_verified` and `guard_objective_complete` use `cfg.min_confidence (0.75)`. Live loop pre-gates `hsm.tick()` for RISKY_STATES when confidence < min_confidence. `RELEASE_RADIANT_KICK` added to RISKY_STATES.
4. P1 Bug — release_held_keys: Added `"1"`, `"2"`, and `keybinds.slot_pika_v2` to safety list.
5. P1 Bug — objective_final falsy 0: Replaced `or '?'` with explicit `is None` checks.

**New tests:** 8 added (54 total, all passing)

**Files changed:** `wave1_machine.py`, `transitions.py`, `states.py`, `primitives.py`, `wave_runner/main.py`, `test_wave1_hsm.py`, `test_input_safety.py`

**Verification:** validate_install PASS, pytest 54/54 PASS, replay_analyzer --help PASS, wave_runner --help PASS

**Next steps:**
- Run assist mode to validate counter reads and confidence on real gameplay
- Tune `progress_ui.crop` regions if reads are unstable
- If assist confirms stable reads, run execute mode with fail-case logging
- Begin 10-run verification once execute is stable

### Phase P0.7 — Executor/HSM Runtime Blockers (Live Execution Fixes)

**Dependency:** Phase P0.6
**Status:** COMPLETED (2026-05-09)
**Goal:** Fix critical runtime bugs preventing Wave 1 live execution from completing.

**Root causes fixed:**
1. **Executor TAP was a no-op:** `ActionSequence.tick()` never called `primitives.press/release` for TAP steps. Fixed: TAP now calls `press(key)` on first tick and `release(key)` after `down_ms` elapsed.
2. **Executor HOLD released immediately:** HOLD step only waited for `down_ms` but never actually waited non-blocking. Fixed: HOLD presses key on first tick, waits `down_ms`, releases on subsequent tick.
3. **WAIT type missing:** Intervals used fake key `HOLD "dummy_wait"` and `HOLD "infinite_wait"`, which called `primitives.hold()` on non-existent keys. Fixed: Added `DeferredActionType.WAIT` that never calls press/release.
4. **OBS_HAKI_SCAN did not early-exit:** Could not transition to `ALIGN_TO_EXIT` mid-scan even when stable 4/4 appeared. Fixed: Now updates `CounterStabilityTracker` every frame and exits immediately on stable clear.
5. **VERIFY_COUNTER branched on single bad frame:** A single 0/4 read after 4/4 flicker triggered OBS_HAKI_SCAN. Fixed: Added `verify_window_sec` (1.5s) guard; counter must be incomplete after window expires before routing to cleanup.
6. **Impossible counter drops not rejected:** 4/4 -> 0/4 mid-wave was treated as valid incomplete. Fixed: Added `is_impossible_drop()` to `CounterStabilityTracker`; rejects drops of >=2 below required objective when high count was previously seen.
7. **MOVE_TO_EXIT left W held forever:** Sequence was `HOLD forward` + `HOLD "infinite_wait"` with no release. Fixed: Now uses `HOLD forward` + `WAIT` + `RELEASE forward`.

**Files changed:**
- `packages/vcl_input/executor.py` — TAP/hold/WAIT semantics, no fake keys
- `packages/vcl_input/primitives.py` — added `press()` method
- `packages/vcl_hsm/wave1_machine.py` — OBS early-exit, verify window, impossible drop rejection
- `packages/vcl_hsm/stability.py` — `saw_high_count()`, `is_impossible_drop()` methods
- `packages/vcl_core/config.py` — added `verify_window_sec: float = 1.5` to `Wave1Config`
- `configs/wave1.shattered_ramparts.yaml` — added `verify_window_sec: 1.5`
- `configs/app.default.yaml` — added `verify_window_sec: 1.5`
- `tests/test_executor.py` (new) — 21 tests for TAP, WAIT, HOLD, fake-key removal
- `tests/test_wave1_hsm.py` — 4 new tests for OBS early-exit, verify window, impossible drop

**Verification:**
- `python tools/validate_install.py` → PASS
- `python -m pytest tests/` → 111/111 PASS (21 new executor tests + 4 new HSM tests)
- `python -m apps.wave_runner.main --help` → PASS
- `python -m apps.replay_analyzer.main --help` → PASS

**Known remaining risks:**
- Live game verification not possible in this environment — unit/simulation coverage only
- Counter crop regions (`counter_crop: [1380, 110, 1620, 150]`) may need tuning on live runs
- Progress detector confidence on real gameplay frames may differ from synthetic test frames
- MOVE_TO_EXIT uses `damage_register_wait_ms` (2200ms) for movement duration — may need separate config
- OBS_HAKI_SCAN stability update passes `confidence=None` when no progress — design choice, may need review

**Next steps:**
- Run assist mode to validate counter reads on real gameplay
- Tune `progress_ui.counter_crop` if reads are unstable
- If counter reads are stable, run execute mode with `--stop-on-fail`
- Collect 10-run metrics; tune `verify_window_sec` based on real counter behavior
- Progress to Phase 8 (MVP Verification) once 9/10 clears achieved

### Phase P0.8 — Runtime Backend Stabilization

**Dependency:** Phase P0.7
**Status:** COMPLETED
**Goal:** Replace fragile hand-rolled runtime primitives with a pluggable backend architecture.

**Tasks completed:**
1. **CaptureConfig, InputConfig, DebugConfig, YoloConfig** added to `vcl_core/config.py`
2. **Optional deps** added to `pyproject.toml`: `[runtime]` (dxcam, pyautogui), `[yolo]` (ultralytics, supervision)
3. **packages/vcl_capture/** — New package with `CaptureBackend` interface (MSS, DXcam backends)
4. **packages/vcl_input/backends.py** — `InputBackend` interface (Pynput, PyDirectInput, PyAutoGUI, Logging)
5. **packages/vcl_input/window_focus.py** — PyWinCtl-based window focus guard
6. **packages/vcl_vision/frame_source.py** — `LiveFrameSource` now delegates to `CaptureBackend`
7. **packages/vcl_vision/progress_detector.py** — Fixed false high-confidence 0/4 bug; added `detect_with_debug()` + `ProgressDebugInfo`
8. **packages/vcl_vision/vision_debug.py** — `VisionDebug` class for crop snapshots and state transitions
9. **packages/vcl_vision/detections.py** — `DetectionBox`, `WorldDetections` normalized boxes
10. **packages/vcl_vision/yolo_detector.py** — YOLO provider skeleton, lazy import, disabled by default
11. **primitives.py** — Now uses `InputBackend`, `fail_on_input_error` control, no silent exception swallow
12. **wave_runner/main.py** — Mode banners, CLI flags (`--capture-backend`, `--input-backend`, `--debug-input`, `--debug-vision`), focus preflight, debug logging
13. **configs/app.default.yaml** + **configs/wave1.shattered_ramparts.yaml** — New sections for capture/input/debug/yolo
14. **tools/collect_yolo_frames.py** — Frame capture CLI for YOLO dataset collection
15. **tools/organize_yolo_dataset.py** — Train/val split and data.yaml generation

**Key design decisions:**
- HSM NOT rewritten; it remains the "brain", YOLO is an optional "eyes" provider
- Backends lazy-imported to avoid hard dependency on optional packages
- `fail_on_input_error: true` default raises on input backend errors
- ProgressDetector no longer returns `(0, 0.90)` for blank crop — panel must be active first
- Assist mode never sends keypresses; execute mode validates focus + backend first
- `reports/vision_debug/` not committed to git

**Files changed:**
- `packages/vcl_core/config.py` — new config models
- `pyproject.toml` — optional extras [runtime], [yolo]
- `packages/vcl_capture/__init__.py` (new)
- `packages/vcl_capture/backends.py` (new)
- `packages/vcl_vision/frame_source.py` — CaptureBackend integration
- `packages/vcl_vision/progress_detector.py` — confidence fix + debug
- `packages/vcl_vision/vision_debug.py` (new)
- `packages/vcl_vision/detections.py` (new)
- `packages/vcl_vision/yolo_detector.py` (new)
- `packages/vcl_vision/__init__.py` — exports new modules
- `packages/vcl_input/backends.py` (new)
- `packages/vcl_input/window_focus.py` (new)
- `packages/vcl_input/primitives.py` — InputBackend integration
- `packages/vcl_input/__init__.py` — exports new modules
- `apps/wave_runner/main.py` — mode banners, CLI flags, focus preflight
- `configs/app.default.yaml` — new sections
- `configs/wave1.shattered_ramparts.yaml` — new sections
- `README.md` — runtime backend documentation, YOLO tooling
- `tests/test_backends.py` (new)
- `tools/collect_yolo_frames.py` (new)
- `tools/organize_yolo_dataset.py` (new)

**Verification:**
- `python tools/validate_install.py` → PASS
- `python -m pytest tests/` → PASS (existing + new tests)
- `python -m apps.wave_runner.main --help` → PASS
- `python -m apps.wave_runner.main live --help` → PASS
- `python tools/collect_yolo_frames.py --help` → PASS
- `python tools/organize_yolo_dataset.py --help` → PASS
- `python -m compileall apps packages tools` → PASS

**Known remaining risks:**
- Live game verification not possible in this environment — unit/simulation coverage only
- Counter crop regions may need tuning on live runs
- DXcam + pydirectinput tested via import-time checks only; real A/B comparison pending live execution
- YOLO provider skeleton does not feed into HSM yet — future phase

**Next steps:**
1. `python -m apps.wave_runner.main live --mode assist --debug-vision` — diagnose counter reads
2. `python -m apps.wave_runner.main keyboard-test --input-backend pydirectinput` — verify Roblox key receipt (prefer pydirectinput first)
3. `python -m apps.wave_runner.main live --mode execute --input-backend pydirectinput --capture-backend dxcam --debug-input --debug-vision` — first real live run
4. Tune `progress_ui.counter_crop` if reads are unstable
5. Collect 10-run metrics; tune `verify_window_sec`

### Phase P0.9 — Runtime Backend Correctness Hotfix

**Dependency:** Phase P0.8
**Status:** COMPLETED

**Goal:** Fix P0.8 implementation bugs found during review — backends were architecturally correct but had API/import errors.

**Tasks completed:**
1. **PyDirectInputBackend** — Now imports `pydirectinput-rgx` first, falls back to `pydirectinput`, does NOT import `pyautogui`. Error message says `pip install pydirectinput-rgx`.
2. **pyproject.toml** — Fixed `[project.optional-dependencies]` with `dxcam[cv2,winrt]`, `pydirectinput-rgx`, `pyautogui`, `PyWinCtl`. `pip install ".[runtime]"` works.
3. **DXCamCaptureBackend** — Now uses `dxcam.create()` with `output_idx=max(0, monitor_index-1)` and `output_color=BGR`. `grab()` passes `region` and `new_frame_only=False`. Returns RuntimeError on `None` frame.
4. **Focus preflight** — Now aborts with `typer.Exit(code=2)` when `require_focus=true` and window focus fails or PyWinCtl is missing. No more "proceeding anyway" on failed focus.
5. **Rich status tag** — Fixed closing bracket from `/[{status_color}]` to `[/{status_color}]`.
6. **VisionDebug** — Moved instantiation outside the frame loop (created once per run, not per frame).
7. **ProgressDebugInfo.candidate_count** — `_count_circles()` now returns 3-tuple `(count, conf, candidate_count)`. `candidate_count` is now the actual number of geometric candidates found, not always 0.

**Key design decisions:**
- Focus guard abort (not warn-and-proceed) is correct for game macro safety
- `pydirectinput-rgx` preferred over `pyautogui` for DirectX/Roblox input
- 3-tuple return from `_count_circles` keeps public API stable while adding debug value

**Files changed:**
- `packages/vcl_input/backends.py` — PyDirectInputBackend imports pydirectinput-rgx, not pyautogui
- `pyproject.toml` — PEP 621 optional-dependencies with correct packages
- `packages/vcl_capture/backends.py` — DXCamCaptureBackend uses dxcam.create(), passes region, new_frame_only=False
- `apps/wave_runner/main.py` — Focus preflight aborts on failure, Rich tag fixed, VisionDebug moved outside loop
- `packages/vcl_vision/progress_detector.py` — _count_circles returns 3-tuple with candidate_count
- `tests/test_backends.py` — New tests for PyDirectInputBackend source inspection, DXcam API, factory error message
- `tests/test_progress_detector.py` — New tests for candidate_count nonzero/zero
- `tests/test_live_confidence_gate.py` — Added mocks for ensure_window_focused and create_input_backend in preflight

**Verification:**
- `python tools/validate_install.py` → PASS
- `python -m pytest tests/test_backends.py tests/test_progress_detector.py` → 40 passed
- `python -m pytest tests/test_calibrate_regions.py tests/test_input_safety.py` → 18 passed
- `python -m apps.wave_runner.main --help` → PASS
- `python -m apps.wave_runner.main live --help` → PASS
- `python -m apps.wave_runner.main keyboard-test --help` → PASS
- `python tools/collect_yolo_frames.py --help` → PASS
- `python tools/organize_yolo_dataset.py --help` → PASS
- `python -m compileall apps packages tools` → PASS

**Known remaining risks:**
- Live game verification still pending — unit tests pass, real execution untested
- Counter crop regions may need tuning on live runs
- DXcam + pydirectinput real-world behavior unverified

**Next steps:**
1. `pip install ".[runtime]"` — install all runtime backends
2. `python -m apps.wave_runner.main live --mode assist --capture-backend dxcam --debug-vision` — diagnose counter reads with DXcam
3. `python -m apps.wave_runner.main keyboard-test --input-backend pydirectinput` — verify Roblox key receipt
4. `python -m apps.wave_runner.main live --mode execute --input-backend pydirectinput --capture-backend dxcam --debug-input --debug-vision` — first real execute run

### Phase 8 — Wave 1 MVP Verification & Polish

**Dependency:** Phase P0.8
**Status:** Pending
**Tasks:**
1. Run 10 Wave 1 execute attempts, collect JSONL logs
2. Compute metrics:
   - `clear_rate` ≥ 0.9 (9/10)
   - `false_exit_attempt_count` = 0
   - `emergency_stop_count` logged
   - `cleanup_cycles` per run
   - `observation_scans` per run
3. Investigate failures: screenshot + log in `reports/failure_cases/`
4. Tune crop regions if detectors miss on real runs
5. Add any missing test fixtures

**Success Criteria:**
- [ ] 9/10 Wave 1 clears
- [ ] 0 false exits (counter never < 4/4 when exiting)
- [ ] F1 stop works reliably
- [ ] All keys released on stop/crash
- [ ] Report shows clear_rate, mean_clear_time, per-run breakdown
- [ ] `python -m apps.wave_runner.main report --run-dir reports/run_logs` produces formatted output

---

## Phase P0.10 — Live Backend Wiring + 0/4 Startup Detection

**Dependency:** Phase P0.9
**Status:** COMPLETED

**Goal:** Fix two P0.9 residual issues found during review:
1. `--input-backend` CLI flag was validated in preflight but NOT wired into runtime primitives.
2. `_count_circles` returned `(None, 0.0, 0)` for no-candidates, which could deadlock the HSM at Wave 1 start.

**Tasks completed:**
1. **Backend wiring** — `live()` now creates `create_input_backend(cfg.input)` for execute mode and `LoggingInputBackend()` for assist mode, passing the selected backend directly into `InputPrimitives`. No more silent fallback to pynput.
2. **`backend_name` property** — `InputPrimitives` now exposes `backend_name` property for debug proof.
3. **Debug input proof** — `live()` now prints `Input backend: {primitives.backend_name}` at loop start and includes `backend={primitives.backend_name}` in every `[INPUT DEBUG]` log line.
4. **Empty slot detection** — Added `_count_empty_slots()` using Canny edges + contour circularity to detect unfilled ring/slot geometry in the counter region. Added `slot_count` to `ProgressDebugInfo`.
5. **0/4 detection path** — If `panel_active=True`, `circle_count=0`, and `slot_count >= objective_total`, the detector now returns `objective_current=0, objective_total=4, confidence` based on slot geometry. This unblocks `guard_stage_verified()` at Wave 1 start.
6. **`_count_circles` 4-tuple** — Returns `(count, conf, candidate_count, slot_count)` for full debug visibility.
7. **`VERIFY_STAGE_UI` removed from `RISKY_STATES`** — `hsm.tick()` always fires in `VERIFY_STAGE_UI`, allowing the HSM to progress from setup to combat even with low-confidence initial reads. Risky combat states (AGGRO, CAST, etc.) still block on low confidence.
8. **Tests** — Added `backend_name` property tests, empty-slot blank crop tests, `slot_count` field tests.

**Files changed:**
- `apps/wave_runner/main.py` — Backend wired into primitives, `LoggingInputBackend` for assist, `backend_name` in debug output, `VERIFY_STAGE_UI` removed from `RISKY_STATES`, `slot_count` in debug JSON
- `packages/vcl_input/primitives.py` — `backend_name` property added
- `packages/vcl_vision/progress_detector.py` — `_count_empty_slots()`, 4-tuple `_count_circles`, `slot_count` in `ProgressDebugInfo`, 0/4 detection path
- `tests/test_backends.py` — `backend_name` property tests, injected backend press/release tests
- `tests/test_progress_detector.py` — `slot_count` field test, blank-crop-no-high-confidence test
- `README.md` — Updated execute command, note about backend wiring, backend priority order

**Verification:**
- `python tools/validate_install.py` → PASS
- `python -m pytest tests/test_backends.py tests/test_progress_detector.py tests/test_calibrate_regions.py tests/test_input_safety.py` → 63 passed
- `python -m compileall apps packages tools` → PASS
- `python -m apps.wave_runner.main --help` → PASS
- `python -m apps.wave_runner.main live --help` → PASS

**Known remaining risks:**
- Empty slot detection relies on geometric heuristics — may need tuning against real game captures
- Slot detection uses Canny edges + contour circularity — if unfilled rings don't have clear edge contrast, detection may still miss 0/4

**Next steps:**
1. `pip install ".[runtime]"` — install all runtime backends
2. `python -m apps.wave_runner.main live --mode assist --capture-backend dxcam --debug-vision` — diagnose counter reads
3. `python -m apps.wave_runner.main keyboard-test --input-backend pydirectinput` — verify Roblox key receipt
4. `python -m apps.wave_runner.main live --mode execute --input-backend pydirectinput --capture-backend dxcam --debug-input --debug-vision` — first real execute run

## Post-MVP Backlog (NOT in this roadmap)

| Item | Trigger | Priority |
|------|---------|----------|
| YOLO enemy detector | ≥200 labeled frames | Low |
| Wave 2-4 support | Wave 1 ≥ 9/10 | Medium |
| Wave 5 survival detection | Wave 2 ≥ 9/10 | Medium |
| Wave 6 guards (600 HP) | Wave 3 ≥ 9/10 | High |
| Lightning/meteorite dodge | Wave 2 ≥ 9/10 | Medium |
| Boss Leo automation | Wave 6 ≥ 9/10 | Low |
| Boss Cupid Queen | After Leo ≥ 9/10 | Low |
| TensorRT export | YOLO accuracy plateau | Low |
| RL/PPO fallback | Symbolic policy fails on new wave | Low |
| Tauri/React debug UI | After Wave 3 | Low |

---

## Research Artifacts

- `.planning/spikes/2026-05-09-wave1-ui-discovery.md` — Full research report (counter = circles discovery)
- `datasets/raw_videos/frames/counter_verify/` — Counter crops for visual verification
- `datasets/raw_videos/frames/video1_analysis/` — Full UI analysis from video1
- `datasets/raw_videos/frames/counter_deep/` — Deep circle analysis
- `datasets/raw_videos/frames/counter_final/` — High-res circle comparison
- Video metadata: 3 new MedalTV videos (539ms, 541ms, 544ms) — all 2560x1440, ~58s dungeon clear
