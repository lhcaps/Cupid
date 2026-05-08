# VisionCombatLab — PROJECT.md

## 1. Project Overview

**Name:** VisionCombatLab (VCL)
**Type:** Screen/video analysis + HSM-driven combat macro for Roblox GPO (Grand Piece Online) Cupid Dungeon.
**Goal (Wave 1 MVP):** Autonomous clear of Shattered Ramparts (Wave 1) using Pika V2, achieving 9/10 clear rate with verifiable reporting.
**Non-Goals:** Full dungeon auto-clear, boss automation, RL/PPO training, client injection, memory/process/network reading, anti-cheat bypass.

---

## 2. Context

### Gameplay Domain
- **Game:** Roblox GPO (Grand Piece Online) — Cupid Dungeon 2026
- **Stage:** Shattered Ramparts (Wave 1)
- **Objective:** Clear 4/4 enemies: 1 katana, 1 bazooka, 2 fists (200 HP each, ~15 damage)
- **Build:** Pika V2 (Starlight Rapier)

### Pika V2 Moveset (from wiki, updated 2026-05-09)

| Key | Move | Stamina | Cooldown | Notes |
|-----|------|---------|---------|-------|
| M1 | Starlight Rapier | 0 | — | Sword combo, scales w/ fruit mastery |
| Q | Starlight Dash | variable | — | 2x distance (HP >70%) |
| E | Blitz Strike | 35 | 13s | Lunge + slam, **stun 1s** |
| R | Radiant Kick | 45 | 13s | Small AoE burst, **blockable** |
| **R (Charged)** | **Radiant Kick Charged** | **45** | **13s** | Gold flash → 3 AoE bursts, **guard-break** |
| Z | Radiant Ray | 66+ | 18s | Maneuverable ray, 6 explosions |
| T | Radiant Flight | 90 | 15s | Fly + damage |
| X | Radiant Jewels | 78 | 30s | Condensed AoE barrage |
| C | Excalibur | 100 | 70s | Massive line AoE, knock-down |

**Critical notes:**
- **Radiant Kick (R) is blockable** — enemies can block it
- **Charged version (gold flash) guard-breaks** enemies
- **Blitz Strike (E)** stuns enemies for 1s — good for cleanup
- **Q dash** has 2x distance when HP >70%

**Wave 1 Strategy:**
1. Setup: press `2` for Pika V2, press `J` for Armament Haki
2. Main combo: hold W+S, geppo Space x5 (aerial advantage)
3. Charged Radiant Kick: hold R until gold flash (~1900ms), release → 3 AoE bursts
4. If Radiant Kick blocked or misses: use Blitz Strike (E) for stun + cleanup
5. Observation Haki (G): scan for remaining enemies when counter < 4/4

**Fallback combo:** M1 Starlight Rapier + E Blitz Strike (35 stamina, 13s cooldown)

### Wave Counter Rendering (CRITICAL — updated 2026-05-09)

**The counter is rendered as filled circles, NOT text "x/4".**

- **Filled circle** (bright center, grayscale >80) = enemy killed
- **Unfilled circle** (dark ring, grayscale <60) = enemy alive
- **Counter region:** `y=100-135, x=1340-1620` (TOP-RIGHT)
- **Wave panel:** `x=1300-1850, y=0-180`

Evidence from video analysis:
```
Lobby (t=0-1s):   0 green pixels  → no wave
Wave 1 (t=2-12s):  551-724 green pixels → wave active
Wave 1 near-clear: 379-432 green pixels → 3-4 kills
Between (t=17-21s): 78-112 green pixels → between waves
Wave 2 (t=22-25s): 631-696 green pixels → wave active
```

**Detection approach:**
1. Crop counter region (y=100-135, x=1340-1620)
2. Grayscale + threshold at brightness=80
3. Connected components on bright regions (filled circles)
4. Filter for circles: aspect ratio 0.5-2.0, area 50-500px
5. Count filled circles = current kills (0 to objective_total)

---

## 3. Architecture

```
apps/
  replay_analyzer/   # CLI: analyze video -> frame extraction, timeline, contact sheet
  wave_runner/       # CLI: dry-run HSM, assist mode, execute mode
packages/
  vcl_core/          # config, schemas, logger, timebase
  vcl_vision/        # frame_source, progress_detector, compass_detector, haki_detector, debug_render
  vcl_hsm/           # wave1_machine, states, transitions
  vcl_input/         # executor, primitives, emergency_stop
  vcl_eval/          # metrics, report
configs/            # YAML: app.default, vision.1440p, wave1.shattered_ramparts, keybinds
datasets/
  raw_videos/        # Source gameplay recordings
  frames/            # Extracted frames from videos
  labels/            # Labeled frames for future YOLO
  fixtures/          # Test fixtures (circle_0_4.png, circle_4_4.png, etc.)
reports/
  debug_videos/      # Annotated debug videos
  run_logs/          # JSONL logs per run
  failure_cases/     # Screenshots + logs for failed runs
  eval/              # Replay analysis output
tools/
  validate_install.py
  extract_frames.py
  extract_new_videos.py
  analyze_new_videos.py
  find_counter_location.py
  verify_counter_circles.py
  analyze_circle_fill.py
  final_circle_analysis.py
tests/
  test_progress_detector.py
  test_compass_detector.py
  test_wave1_hsm.py
```

---

## 4. Stack

| Group | Tech | Purpose |
|-------|------|---------|
| Language | Python 3.11+ | Fast iteration, rich CV ecosystem |
| Screen/video I/O | OpenCV, mss | Video decode, live screen capture |
| UI Counter | OpenCV circle fill detection | Detect 0-4 filled circles |
| Compass | OpenCV threshold + contour analysis | Read heading label near screen center |
| Object detection | Deferred YOLO | Detect NPC/Haki outline (after ≥200 labels) |
| Data schema | Pydantic v2 | GameState, Wave1Action validation |
| CLI | Typer + Rich | `vcl analyze`, `vcl wave1-run`, reporting |
| Config | YAML | Stage config, keybinds, crop regions |
| Input | pynput | Local key press with emergency stop |
| Logging | JSONL | Per-state/action/frame logs |
| Testing | pytest | Unit tests for detectors and HSM |

---

## 5. Principles (Karpathy Guidelines)

1. **Think Before Coding** — Surface assumptions, ask when unclear. Wave 1 is a state+timing+UI problem, not a complex object detection problem.
2. **Simplicity First** — No YOLO, no RL, no full dungeon. Only what's needed to clear Wave 1.
3. **Surgical Changes** — Edit only files that need changing per phase. No speculative refactors.
4. **Goal-Driven Execution** — Each phase has explicit success criteria; loop until verified.

---

## 6. Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Counter misread (filled circle detection fails) | **CRITICAL** | Circle fill detection with confidence gate; never exit if confidence < 0.75 |
| Compass fails to read heading | MEDIUM | Max rotate timeout 3s; stop and pause if timeout |
| Charged R misfires (released too early) | HIGH | Fixed charge window ~1900ms from config; gold flash visual confirmation |
| Radiant Kick blocked by enemies | HIGH | Blitz Strike (E) fallback for stun + cleanup; max 2 cleanup cycles |
| Emergency stop fails | **CRITICAL** | F1 stops all keys; Ctrl+C releases all keys; on-exception screenshot |
| False exit (counter < 4/4) | **CRITICAL** | HSM never transitions to ALIGN_TO_EXIT unless filled circle count == objective_total |
| Auto-clear blocks manual play | LOW | Mode is explicit (`--mode execute`); assist mode first |

---

## 7. Definition of Done (Wave 1 MVP)

- [ ] Replay analyzer runs on supplied video without crash
- [ ] Progress detector reads stage + counter (filled circles) with ≥90% accuracy on sampled frames
- [ ] Compass detector reads heading with ≥85% accuracy
- [ ] HSM dry-run produces correct action sequence
- [ ] Emergency stop (F1) releases all keys and saves screenshot
- [ ] 9/10 Wave 1 clears in execute mode
- [ ] 0 false exits while circle count < 4
- [ ] JSONL report includes: run_id, state, progress, compass, action, confidence, duration_sec
- [ ] Key constraint: no memory injection, no process read, no network call, no anti-cheat interaction

---

## 8. Dungeon Stages (All 8 — for future reference)

| # | Name | Enemies | Counter | HP | Damage | Hazard |
|---|------|---------|---------|-----|--------|-------|
| 1 | Shattered Ramparts | 4/4 | 4 circles | 200 | 15 | Easy |
| 2 | The Forsaken Garden | 4/4 | 4 circles | 200 | 16 | Lightning (46dmg) |
| 3 | The Scarlet Plaze | 5/5 | 5 circles | 200/600 | 15/33 | Lightning + meteorite |
| 4 | The Scarlet Ruins | 7/7 | 7 circles | 200 | 15 | + arrows (22/hit) |
| 5 | Endure Cupid's Wrath | 5 waves | NO counter | — | 15/hit | Arrows, heals |
| 6 | Heartguard's Keep | 6/6 | 6 circles | **600** | 33 | Arrows after |
| 7 | Leo's Inferno | Boss | Boss | 3750 | varies | Grounded |
| 8 | Defeat Cupid Queen | Boss (4 stages) | Boss | varies | varies | Tower phase |
