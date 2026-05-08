# VisionCombatLab Design Context

## Design Register

Screen-based combat automation. The interface is a terminal/CLI tool with JSONL logs and Rich-formatted reports. No web UI needed.

## Design Settings

- OUTPUT: CLI + JSONL logs
- VISUAL_DENSITY: terminal-focused
- UI_STYLE: Rich console output with colored panels

## Design Decisions

### Terminal-First

- All output via Rich console (colored panels, tables, progress bars)
- JSONL for machine-readable logs
- No web UI for MVP

### CLI Structure

```bash
vcl analyze --video <path>          # Video frame extraction
vcl simulate --timeline <json>        # HSM dry-run
vcl live --mode assist              # Assist mode (print actions)
vcl live --mode execute             # Execute mode (press keys)
vcl report --run-dir <path>         # Generate report
vcl keyboard-test                   # Test keyboard input
```

### Log Format

```json
{"run_id": "...", "timestamp": 1.23, "state": "AGGRO_WITH_GEPPO", "action": "GEPPO_STACK", "progress": "2/4", "compass": "S", "confidence": 0.85}
```

### Safety Design

- F1 emergency stop (pynput listener)
- Ctrl+C handler releases all keys
- Screenshot on failure
- Configurable timeouts

## Visual Design

### Rich Console Colors

- **Cyan:** State transitions, headers
- **Green:** Success, clear
- **Red:** Failure, emergency stop
- **Yellow:** Warnings, low confidence
- **Dim:** Timestamps, debug info

### Report Format

```
=== Wave 1 Run Summary ===
Run ID: wave1_20260509_063000_abcd12
Status: CLEAR
Duration: 18.3s
Radiant Kicks: 1
Observation Scans: 0
Cleanup Cycles: 0

Clear Rate: 9/10
Mean Clear Time: 17.2s
```
