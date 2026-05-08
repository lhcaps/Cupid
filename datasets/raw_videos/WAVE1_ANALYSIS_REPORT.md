# Wave 1 Shattered Ramparts - Video Analysis Report

## Video Metadata

| Property | Value |
|----------|-------|
| **Resolution** | 2560x1440 |
| **FPS** | 59.95 |
| **Total Frames** | 4764 |
| **Duration** | 79.47 seconds (1.32 minutes) |
| **Format** | MP4 |

---

## 1. UI Elements Analysis

### 1.1 Progress UI Panel (Top-Left)

**Location:** `(x: 50-350, y: 50-150)` at 2560x1440 resolution

**Counter Format:** `"X/4"` where:
- `X` = Large, bold, white number (current kills)
- `/4` = Smaller white text (total enemies in wave)
- Example: `0/4`, `1/4`, `2/4`, etc.

**Visual Characteristics:**
- Background: Dark semi-transparent panel with visible border
- Panel shows "CUPID" text with heart symbol
- Orange/gold accent color for UI elements
- White text with drop shadow for readability

**Suggested Crop Region:**
```python
# For 2560x1440 resolution
progress_roi = (50, 50, 300, 100)  # x, y, width, height
```

### 1.2 Compass Bar (Top-Center)

**Location:** `(x: 850-1700, y: 40-120)` at 2560x1440 resolution

**Labels:** N, NE, E, SE, S, SW, W, NW (8 cardinal directions)

**Visual Characteristics:**
- Horizontal bar with directional labels
- Red/orange indicator/marker pointing to current direction
- Labels are uppercase letters
- Semi-transparent dark background

**Suggested Crop Region:**
```python
# For 2560x1440 resolution
compass_roi = (850, 40, 850, 80)  # x, y, width, height
```

---

## 2. Gameplay Sequence Analysis

### Wave 1 Enemies
Based on frame analysis:
- **t=0-5s:** Counter changes from `0/4` to `1/4` (first kill)
- **t=5-10s:** Counter remains `1/4` (combat continues)
- **t=10-20s:** Counter appears at `1/4`
- **t=20-30s:** Counter appears at `1/4` or `2/4`
- **t=30s:** Counter appears at `1/4` or `2/4`

### Attack Pattern Observed
- Player uses Geppo (空中移動) for mobility
- Charged R attack visible (gold flash effect)
- Player moves fluidly between enemies

### Counter Changes
The counter increments when enemies are killed:
- `0/4` → `1/4` → `2/4` → `3/4` → `4/4` → Clear

---

## 3. Color Analysis

| Element | Color (BGR) | Notes |
|---------|-------------|-------|
| Counter Text | White (255, 255, 255) | Main kill count |
| UI Panel Background | Dark semi-transparent | ~50% opacity |
| Accent/Border | Orange/Gold | UI highlights |
| Compass Indicator | Red/Orange | Direction marker |

**Brightness Levels:**
- Counter area avg brightness: 143.7 (mid-range)
- Compass area avg brightness: 121.5 (slightly darker)
- Top bar avg brightness: 137.1

---

## 4. Recommended Crop Regions

### For 2560x1440 Resolution

```python
# Progress UI (top-left)
PROGRESS_CROP = {
    'x1': 50, 'y1': 50,
    'x2': 350, 'y2': 150
}

# Compass (top-center)
COMPASS_CROP = {
    'x1': 850, 'y1': 40,
    'x2': 1700, 'y2': 120
}

# Full top UI bar
TOP_UI_BAR = {
    'x1': 0, 'y1': 0,
    'x2': 2560, 'y2': 200
}
```

### Scale Factors for Other Resolutions

To adapt to other resolutions, apply scale factors:
```python
scale_x = current_width / 2560
scale_y = current_height / 1440
```

---

## 5. Improvements for Detector Code

### 5.1 ProgressDetector Updates

**Current pattern (to improve):**
- Look for "X / 4" with spaces
- Consider variations: "X/4" without spaces

**Recommended changes:**
```python
# More flexible counter pattern
counter_patterns = [
    r'\d+\s*/\s*\d+',      # "1 / 4" or "1/ 4"
    r'[\u4e00-\u9fff]+\s*\d+\s*/\s*\d+',  # Chinese + counter
]

# Check for both "CUPID" text and counter
cupid_text_detected = check_for_cupid_ui(cropped_region)
```

### 5.2 CompassDetector Updates

**Current pattern:**
- Look for full 8 directions: N, NE, E, SE, S, SW, W, NW

**Recommended changes:**
```python
# More robust compass detection
# Only require 4 cardinal directions visible
cardinal_directions = ['N', 'E', 'S', 'W']
intercardal_directions = ['NE', 'SE', 'SW', 'NW']

# Compass bar has unique red/orange marker
marker_color_range = ((0, 50, 200), (30, 100, 255))  # HSV orange-red
```

### 5.3 General Improvements

1. **Threshold adjustment:** Current brightness threshold (140) may need tuning
2. **Multi-resolution support:** Add scale factors for different game resolutions
3. **Robust pattern matching:** Handle both "X/4" and "X / 4" formats
4. **Color-based verification:** Check for orange/gold UI accents

---

## 6. Key Observations for Automation

### Screen Resolution
- Native: 2560x1440
- All coordinates provided for this resolution
- Scale factors needed for other resolutions

### Visual Patterns
1. **Progress UI:**
   - Always in top-left corner
   - Has distinctive "CUPID" branding
   - Dark panel with white text
   - Counter "X/4" format

2. **Compass:**
   - Top-center of screen
   - 8 direction labels
   - Red/orange indicator
   - Horizontal bar format

### Detection Hints
- Counter region has moderate brightness (avg 143.7)
- Compass region is slightly darker (avg 121.5)
- Orange/gold accent colors are consistent markers
- UI elements have semi-transparent dark backgrounds

---

## 7. Frame Extract Timeline

Extracted frames saved to: `e:/Macro/Cupid/datasets/raw_videos/frames/`

Key frames:
- `frame_t00s.png` - Start of wave
- `frame_t05s.png` - After first kill
- `frame_t10s.png` - Mid-combat
- `frame_t15s.png` - Continued combat
- `frame_t20s.png` - Progress check
- `frame_t25s.png` - Progress check
- `frame_t30s.png` - Final clears

---

## 8. Next Steps

1. **Update ProgressDetector:**
   - Handle "X/4" and "X / 4" patterns
   - Add "CUPID" text detection for verification
   - Adjust crop region to (50, 50, 300, 100)

2. **Update CompassDetector:**
   - Handle partial direction labels
   - Add color-based marker detection
   - Adjust crop region to (850, 40, 850, 80)

3. **Testing:**
   - Test with extracted frames
   - Verify detection on gameplay footage
   - Fine-tune thresholds

---

*Analysis completed: 2026-05-09*
*Frames extracted from: MedalTVRoblox20260509053121278-trim-1778279513526.mp4*
