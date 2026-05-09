# VisionCombatLab

Screen-based combat automation for Roblox GPO (Grand Piece Online) Cupid Dungeon using Pika V2.

**Wave 1 MVP:** Autonomous clear of Shattered Ramparts at 9/10 success rate.

Full documentation: [docs/README.md](docs/README.md)

Full roadmap: [.planning/ROADMAP.md](.planning/ROADMAP.md)

Project context: [PROJECT.md](PROJECT.md)

## What It Does

VCL observes game UI elements (wave counter, compass) via screen capture and executes combat actions (geppo jumps, charged Radiant Kick, observation haki) using a hierarchical state machine. No memory injection, no process reading.

## Architecture

```
apps/           CLI tools: replay analyzer, wave runner
packages/
  vcl_core/    Config, schemas, logger
  vcl_vision/  Frame capture, progress detector (circle fill), compass detector
  vcl_hsm/     Wave1HSM state machine
  vcl_input/   Keyboard primitives, executor, emergency stop
  vcl_eval/     Metrics, report generation
configs/        YAML stage configs
datasets/       Raw videos, extracted frames, fixtures
reports/        Run logs, failure cases
```

## Quick Start

```bash
pip install opencv-python numpy pydantic pyyaml typer rich mss pynput pytest ruff
python tools/validate_install.py
pytest tests/

# Analyze a gameplay video
python -m apps.replay_analyzer.main analyze --video path/to/video.mp4 --out reports/eval/

# Assist mode (print actions, no key presses) — safe diagnosis
python -m apps.wave_runner.main live --mode assist

# Execute mode (full automation)
python -m apps.wave_runner.main live --mode execute

# Optional: install runtime backends for better game compatibility
pip install ".[runtime]"   # dxcam + pyautogui
pip install ".[yolo]"       # ultralytics + supervision

# Optional: collect YOLO training frames
python tools/collect_yolo_frames.py --out datasets/yolo_raw/run1 --duration-sec 60

# Generate report
python -m apps.wave_runner.main report --run-dir reports/run_logs
```

## Runtime Backends

VCL uses pluggable backends for screen capture and keyboard input:

### Capture Backend (`--capture-backend`)
| Backend | Install | Best For |
|---------|---------|----------|
| `mss` (default) | Included | General screen capture |
| `dxcam` | `pip install dxcam` | Windows/DirectX games, low-latency |

### Input Backend (`--input-backend`)
| Backend | Install | Best For |
|---------|---------|----------|
| `pynput` (default) | Included | General keyboard input |
| `pyautogui` | `pip install pyautogui` | DirectX games, SendInput() |

### Window Focus Guard
Before execute mode, VCL checks that the Roblox window is focused.
Install PyWinCtl for automatic window management:
```bash
pip install pywinctl
```

## Debug Vision

Save crop snapshots and detector overlays for diagnosis:

```bash
python -m apps.wave_runner.main live --mode assist --debug-vision
# Saves to reports/vision_debug/<run_id>/
#   - frame_<ts>.png          (full frame)
#   - progress_crop_<ts>.png   (progress UI region)
#   - counter_crop_<ts>.png   (circle counter region)
#   - debug_<ts>.json        (detector debug metadata)
```

## YOLO Dataset Collection (Optional)

Collect frames for future YOLO training:

```bash
# 1. Collect raw frames
python tools/collect_yolo_frames.py --out datasets/yolo_raw/run1 --duration-sec 120 --fps 10

# 2. Annotate with CVAT (export as YOLO format)

# 3. Organize into train/val splits
python tools/organize_yolo_dataset.py \
    --images datasets/yolo_raw/run1/images \
    --output datasets/yolo_dataset \
    --split 0.8

# 4. Train (when dataset is ready)
# pip install ".[yolo]"
# ultralytics train --data datasets/yolo_dataset/data.yaml ...
```

**Note:** YOLO is disabled by default. Set `yolo.enabled: true` in config to enable.

## Wave 1 Combat Flow

```
BOOT → WAIT_PLAYER_CONTROL → SETUP_PIKA_V2 → ENTER_STAGE
→ VERIFY_STAGE_UI → AGGRO_WITH_GEPPO → CAST_CHARGED_RADIANT_KICK
→ VERIFY_COUNTER
    → ALIGN_TO_EXIT (if 4/4)
    → OBS_HAKI_SCAN (if < 4/4)
→ CLEANUP_IF_NEEDED → VERIFY_COUNTER_AGAIN → ALIGN_TO_EXIT
→ MOVE_NEXT_STAGE → CONFIRM_STAGE_TRANSITION → DONE
```

## Key Discovery: Counter is Circles, Not Text

Wave counter renders as **filled circles** (enemy killed) vs unfilled (enemy alive), not text "x/4". Detection uses grayscale threshold + connected components + circle shape filter.

## Key Constraints

- No memory injection — screen capture only
- No process reading — no internal game state
- No network calls — no anti-cheat interaction
- Safety first — F1 emergency stop always available

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 1 | Foundation | Done |
| 2 | Replay Analyzer | Done |
| 3 | Progress Detector | In Progress |
| 4 | Compass Detector | Done |
| 5 | Wave 1 HSM | Done |
| 6 | Input Primitives | Done |
| 7 | Live Runner | Done |
| 8 | MVP Verification | Pending |

Full breakdown: `.planning/ROADMAP.md`

Design context: [docs/DESIGN.md](docs/DESIGN.md)

## References

- [GPO Cupid Dungeon Wiki](https://grand-piece-online.fandom.com/wiki/Cupid_Dungeon_2026)
- [Pika Pika no Mi Moveset](https://grand-piece-online.fandom.com/wiki/Pika_Pika_no_Mi/Fruit_Moveset)
