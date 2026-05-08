# Gameplay Analysis Report — MedalTVRoblox20260509053121278-trim.mp4

## Video Metadata

| Property | Value |
|----------|-------|
| Resolution | 2560x1440 |
| FPS | 59.95 |
| Total Frames | 4764 |
| Duration | 79.5 seconds |
| File | MedalTVRoblox20260509053121278-trim-1778279513526.mp4 |

## UI Element Locations (2560x1440)

### 1. Wave Progress Counter "x/4"
- **Position:** TOP-RIGHT area
- **Counter region:** x=1380-1620, y=110-150 (~240x40px)
- **Wave panel:** x=1500-1760, y=0-100 (~260x100px)
- **Combined crop:** x=1300-1850, y=0-180 (~550x180px)
- **Format:** "x/4" where x = 0, 1, 2, 3, or 4
- **Color:** Text appears in UI overlay (various colors)

### 2. Compass / Direction Indicator
- **Position:** TOP CENTER
- **Region:** x=1200-1400, y=10-60 (~200x50px)
- **Format:** Single letter indicator (N, NE, E, SE, S, SW, W, NW)
- **Color:** White/light text, ~35px character height
- **Behavior:** Fixed single-character indicator pointing to current heading

### 3. Health Bar
- **Position:** BOTTOM-LEFT
- **Region:** x=0-400, y=1290-1440 (~400x150px visible)
- **Color:** Red bar (health), white/gray border

### 4. Stage/Dungeon Name
- **Position:** TOP area
- **Appears:** During announcements and victory/defeat screens
- **Frames:** 22-24, 36-38 (likely victory announcements)

## Gameplay Timeline

| Time | Phase | Events |
|------|-------|--------|
| 0-4s | Lobby | No wave active, no combat |
| 4-18s | Wave 1 | Wave active, light combat, announcements visible |
| 18-32s | Between | Heavy combat, wave UI hidden |
| 32-44s | Wave 2 | Wave UI returns, heavy combat |
| 44-56s | Between | Heavy combat continues |
| 56-68s | Wave 3 | Wave UI active, combat |
| 68-76s | Wave 4/Final | Wave UI visible |
| 76-79.5s | Victory | Stage name announcement appears |

## Key Observations for Automation

### Counter Detection
- Counter "x/4" is in TOP-RIGHT, NOT top-left as originally assumed
- Need to crop x=1380-1620, y=110-150 for the counter
- The wave panel in x=1500-1760, y=0-100 confirms wave is active
- Need to distinguish between:
  - Lobby (no wave active, no UI): conf=0.0
  - Wave active (wave panel visible): conf>0.3
  - Counter 0/4 through 4/4

### Compass Detection
- Compass is a single-character indicator in TOP CENTER
- The indicator is ~35px wide, 40px tall
- 8 possible positions: N, NE, E, SE, S, SW, W, NW
- Active direction is highlighted (brighter/whiter)
- Search region: x=1200-1400, y=10-60

### Wave Sequence
- There are 4 waves in the dungeon, not just 1
- Wave 1 (0/4) appears at ~4s
- Wave 2 appears at ~32s
- Wave 3 appears at ~56s
- Wave 4 appears at ~68s
- Victory/clear screen at ~76s

### Combat Observations
- Heavy combat phases happen between wave announcements
- The player used various attacks (M1, E, R, Q dashes)
- Charged R was used (visible kick effect in some frames)
- Player maintains aerial position (geppo) during combat

## Recommended Crop Regions (2560x1440)

```yaml
progress_ui:
  crop: [1300, 0, 1850, 180]
  counter_crop: [1380, 110, 1620, 150]
  wave_panel_crop: [1500, 0, 1760, 100]

compass:
  crop: [1200, 10, 1400, 60]
```

## Gameplay Notes
- Video shows a full dungeon run (4 waves), not just Wave 1
- The counter resets for each new wave
- Stage name "Shattered Ramparts" appears on victory announcement
- Exit direction varies per wave (may not always be "S")
