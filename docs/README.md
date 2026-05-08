# VisionCombatLab — Cupid Dungeon Automation

**Status:** MVP in progress (Wave 1 MVP)

**Focus:** Screen-based combat automation for Roblox GPO Cupid Dungeon 2026 using Pika V2 build.

---

## What This Is

VisionCombatLab (VCL) is a screen-analysis + hierarchical state machine (HSM) system that autonomously clears Wave 1 (Shattered Ramparts) in the Cupid Dungeon event of Grand Piece Online (Roblox). It uses:

- **OpenCV** for real-time screen capture and UI element detection
- **Python HSM** for decision-making (symbolic planning, no ML)
- **pynput** for keyboard input automation

The system observes game UI elements (wave counter, compass heading) and executes combat actions (geppo jumps, charged Radiant Kick, observation haki) without memory injection or process reading.

---

## Architecture

```
apps/
  replay_analyzer/   CLI: video -> frame extraction, timeline, contact sheet
  wave_runner/       CLI: dry-run HSM, assist mode, execute mode
packages/
  vcl_core/         Config, Pydantic schemas, JSONL logger
  vcl_vision/       Frame source, progress detector (circles), compass detector, haki detector
  vcl_hsm/          Wave1HSM state machine, transition guards
  vcl_input/        Input primitives, executor, emergency stop
  vcl_eval/         Metrics, report generation
configs/             YAML configs per stage/resolution
datasets/
  raw_videos/       Source gameplay recordings + extracted frames
  fixtures/          Test fixtures for detector validation
reports/             Debug videos, run logs, failure cases
tools/               Frame extraction, analysis, validation scripts
tests/               pytest unit tests
```

---

## Wave 1 MVP

**Goal:** Clear 4/4 enemies (1 katana, 1 bazooka, 2 fists) with Pika V2 Charged Radiant Kick at 9/10 success rate.

### Combat Flow

1. **Setup:** Press `2` (Pika V2) + `J` (Armament Haki)
2. **Aggro:** Geppo stack (hold W+S, rapid Space x5)
3. **Attack:** Charged Radiant Kick (hold R ~1900ms until gold flash, release)
4. **Verify:** Check wave counter — if < 4/4, scan with Observation Haki
5. **Cleanup:** Blitz Strike (E) if Radiant Kick blocked
6. **Exit:** Align compass to target heading, move to next stage

### Key Mechanics (from wiki)

| Move | Key | Stamina | Cooldown | Notes |
|------|------|---------|---------|-------|
| Starlight Rapier | M1 | 0 | — | Basic sword combo |
| Blitz Strike | E | 35 | 13s | Lunge + slam + stun 1s |
| **Radiant Kick** | R | 45 | 13s | Small AoE (blockable) |
| **Radiant Kick (Charged)** | R | 45 | 13s | **Gold flash → 3 AoE bursts, guard-break** |

**Critical:** Radiant Kick is blockable. Charged version guard-breaks enemies after gold flash.

---

## Wave Counter Detection

**CRITICAL DISCOVERY (2026-05-09):** The wave counter renders as **filled circles**, not text.

- **Filled circle** (bright center) = enemy killed
- **Unfilled circle** (dark ring) = enemy alive
- **Counter region:** `y=100-135, x=1340-1620` (TOP-RIGHT at 2560x1440)
- **Detection:** Grayscale threshold + connected components + circle shape filter

Evidence from video analysis:

```
Lobby (t=0-1s):   0 green pixels  → no wave
Wave 1 (t=2-12s):  551-724 green pixels → wave active
Between (t=17-21s): 78-112 green pixels → between waves
```

---

## Dungeon Stages

| # | Name | Enemies | Counter | HP | Hazard |
|---|------|---------|---------|-----|--------|
| 1 | Shattered Ramparts | 4/4 | 4 circles | 200 | Easy |
| 2 | The Forsaken Garden | 4/4 | 4 circles | 200 | Lightning (46dmg) |
| 3 | The Scarlet Plaze | 5/5 | 5 circles | 200/600 | Lightning + meteorite |
| 4 | The Scarlet Ruins | 7/7 | 7 circles | 200 | + arrows (22/hit) |
| 5 | Endure Cupid's Wrath | 5 waves | NO counter | — | Arrows, heals |
| 6 | Heartguard's Keep | 6/6 | 6 circles | **600** | Arrows after |
| 7 | Leo's Inferno | Boss | Boss | 3750 | Grounded |
| 8 | Defeat Cupid Queen | Boss (4 stages) | Boss | varies | Tower phase |

---

## Getting Started

```bash
# Install dependencies
pip install opencv-python numpy pydantic pyyaml typer rich mss pynput pytest ruff

# Validate installation
python tools/validate_install.py

# Run tests
pytest tests/

# Analyze a gameplay video
python tools/extract_frames.py --video path/to/video.mp4 --out datasets/frames/

# Simulate HSM over a recorded timeline
python -m apps.wave_runner.main simulate --timeline timeline.json --config configs/wave1.shattered_ramparts.yaml

# Run assist mode (prints actions, no key presses)
python -m apps.wave_runner.main live --mode assist

# Run execute mode (full automation)
python -m apps.wave_runner.main live --mode execute
```

---

## Phase Status

See `.planning/ROADMAP.md` for full phase breakdown.

Project context: [PROJECT.md](../PROJECT.md) (root)

Design context: [DESIGN.md](DESIGN.md)

| Phase | Name | Status |
|-------|------|--------|
| 1 | Foundation | Done |
| 2 | Replay Analyzer | Done |
| 3 | Progress Detector | **In Progress (rewrite needed)** |
| 4 | Compass Detector | Done |
| 5 | Wave 1 HSM | Done |
| 6 | Input Primitives | Done |
| 7 | Live Runner | Done |
| 8 | MVP Verification | Pending |

---

## Dataset

- **Videos:** 4 MedalTV gameplay recordings (2560x1440, ~60fps, ~58-79s each)
- **Frames:** Extracted at 0.5-1s intervals to `datasets/raw_videos/frames/`
- **Analysis:** Counter crops, compass crops, UI crops saved per video
- **Fixtures:** Test fixtures in `datasets/fixtures/`

---

## Research Artifacts

- `.planning/spikes/2026-05-09-wave1-ui-discovery.md` — Counter = circles discovery
- `datasets/raw_videos/frames/counter_verify/` — Counter crops for verification
- `datasets/raw_videos/frames/video1_analysis/` — Full UI analysis
- `datasets/raw_videos/WAVE1_ANALYSIS_REPORT.md` — Original analysis

---

## Key Constraints

- **No memory injection** — screen capture only
- **No process reading** — no internal game state access
- **No network calls** — no anti-cheat interaction
- **Local keyboard only** — pynput for key presses
- **Safety first** — F1 emergency stop, Ctrl+C cleanup

---

## References

- [GPO Cupid Dungeon Wiki](https://grand-piece-online.fandom.com/wiki/Cupid_Dungeon_2026)
- [Pika Pika no Mi Moveset](https://grand-piece-online.fandom.com/wiki/Pika_Pika_no_Mi/Fruit_Moveset)
