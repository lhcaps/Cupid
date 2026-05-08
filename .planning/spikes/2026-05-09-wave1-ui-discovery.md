# Research Report: Wave 1 UI Counter Discovery + Cross-Video Analysis

## Executive Summary

Analysis of 3 new MedalTV gameplay videos (2026-05-09 05:39-05:44) + wiki cross-reference reveals that **the entire counter detection approach is fundamentally wrong**. The wave counter is rendered as filled vs unfilled circles, not text. This discovery invalidates the current `progress_detector.py` blob-analysis approach and requires a complete rewrite.

---

## Finding 1: CRITICAL — Counter Rendering is Circles, NOT Text

### Evidence

**HSV Analysis:**
| State | Green Pixels (1250-1700, y=90-160) | Dark Pixels |
|-------|--------------------------------------|-------------|
| Lobby (t=0-1s) | **0** | 17,500 (100%) |
| Wave 1 (t=2-12s) | **551-724** | ~9,067 (~52%) |
| Wave 1 near-clear (t=13-16s) | **379-432** | ~7,287 (~42%) |
| Between-waves (t=17-21s) | **78-112** | ~8,115 |
| Wave 2 (t=22-25s) | **631-696** | ~7,612 |

**Green dominance:** `green = g > r * 1.1 AND g > b * 1.1` in the counter region.

**Diff analysis (lobby vs wave):**
- Top diff region: `(1416, 101)` — area=86,269 pixels
- Counter region `y=100-135, x=1340-1620` confirmed as active wave indicator

**Brightness distribution during wave (450x50 crop at y=100-150):**
- Very dark (0-30): 2,821 px (17.6%)
- Dark (30-80): 6,906 px (43.2%) — **unfilled circle rims**
- Mid (80-150): 4,390 px (27.4%) — **UI panel background**
- Bright (150-220): 1,883 px (11.8%) — **filled circle centers + UI text**

**Visual confirmation:** Crops saved at `datasets/raw_videos/frames/counter_verify/` show:
- Dark rings (unfilled circles) with bright/green centers (filled circles)
- The filled circles are brighter than the dark unfilled circles
- 4 circles visible in the counter row

### Conclusion

The wave counter renders as a **horizontal row of 4 circles**:
- **Filled circle** (bright center) = enemy killed
- **Unfilled circle** (dark ring) = enemy alive
- Circle rendering uses green/dark color scheme
- Counter value = **count of filled circles** (0-4)

### Current Code is Wrong

| Current Approach | Reality |
|-----------------|---------|
| Invert dark threshold | Circles are rendered in mixed brightness |
| Find digit blobs | No text digits exist |
| Estimate digit from area | Irrelevant — circles not digits |
| `x/4` text pattern | Never rendered as text |

---

## Finding 2: Counter Region (Verified)

| Parameter | Value |
|-----------|-------|
| Counter row Y | 100-135 (pixel row of circles) |
| Counter row X | 1340-1620 (4 circles horizontally spaced) |
| Circle radius | ~10-15 pixels |
| Circle spacing | ~40-50 pixels apart |
| Filled color | Bright (grayscale >80) + green-dominant |
| Unfilled color | Dark (grayscale <60) |

**Combined progress UI area:** `x=1300-1850, y=0-180` (TOP-RIGHT)
**Wave panel:** `x=1500-1760, y=0-100` (contains wave name + circle counter)

---

## Finding 3: Wave Timing (All 3 Videos)

| Video | Duration | FPS | Wave 1 Window | Pattern |
|-------|----------|-----|----------------|---------|
| 539ms | 58.27s | 59.98 | ~2-25s | wave→between→wave 2→... |
| 541ms | 58.25s | 59.95 | ~2-25s | Similar pattern |
| 544ms | 58.32s | 59.93 | ~2-25s | Similar pattern |

All videos show **full dungeon run** (all 8 stages) in ~58s. This is faster than the original video (79.5s) — possibly due to better build/gear or skill level.

---

## Finding 4: Counter Transitions (video1)

Green pixel count in counter region over time:

```
t=0-1s:    0     (LOBBY - no wave)
t=2s:      681   (WAVE 1 START)
t=2-12s:   551-724 (Wave 1 active, 0-2 kills)
t=13-16s:  379-432 (Wave 1 nearly complete, 3-4 kills)
t=17-21s:  78-112  (Between waves - UI different)
t=22-25s:  631-696 (WAVE 2 active)
t=26-29s:  0       (Between waves - no wave active)
t=30s+:    Varies  (Subsequent waves)
```

The **green pixel count changes** as enemies are killed. However, tracking individual kills via green pixel count alone is noisy — a better approach is to **count filled circles directly**.

---

## Finding 5: Compass Detection

- **Location:** `x=1200-1400, y=10-60` (TOP CENTER, single letter indicator)
- Compass single-letter: N, NE, E, SE, S, SW, W, NW
- **Blob count:** stays at 1 during waves, spikes to 13-16 at ~39-41s (arrow phase / stage transition)
- HoughCircles finds ~350 circles in compass region — likely decorative elements
- Compass detection logic in `compass_detector.py` should still work with threshold + contour approach

---

## Finding 6: Wave 1 Strategy Analysis

### Why Radiant Kick Should One-Shot Wave 1

| Enemy | HP | Damage |
|-------|-----|--------|
| 1 katana | 200 | 15 |
| 1 bazooka | 200 | 15 |
| 2 fists | 200 | 15 |
| **Total** | **800** | - |

Pika V2 Charged Radiant Kick: 3 AoE bursts, each dealing significant damage. At 1900ms charge, should deal ~800+ total damage across 4 clustered enemies.

### Cleanup Strategy (If Radiant Kick Misses)

1. **Observation Haki (G):** Tap G to scan for remaining enemies (opaque dark silhouettes)
2. **Blitz Strike (E):** Fallback melee attack for cleanup
3. **M1 (auto-attack):** Basic combo if other abilities on cooldown

### Geppo + Forward Movement

- Hold W+S during geppo stack to stay in place
- Rapid Space taps (5x at 100-180ms intervals)
- Maintain aerial position for AoE targeting

---

## Finding 7: Dungeon Stages (from Wiki + Video)

### Wave 1 (Shattered Ramparts) — Wave 1 Target

| Attribute | Value |
|-----------|-------|
| Enemies | 4/4: 1 katana, 1 bazooka, 2 fists |
| HP | 200 each |
| Damage | 15 each |
| Counter | 4 circles |
| Difficulty | Easy |

### Wave 2 (The Forsaken Garden)

| Attribute | Value |
|-----------|-------|
| Enemies | 4/4: 4 katana |
| HP | 200 each |
| Damage | 16 each |
| Counter | 4 circles |
| Hazard | Lightning (46 dmg) — red circle warning |
| Difficulty | Easy |

### Wave 3 (The Scarlet Plaze)

| Attribute | Value |
|-----------|-------|
| Enemies | 5/5: 2 pistol, 1 melee, 1 kiribachi, 1 guard |
| HP | 200 (10 pistol), 600 (guard) |
| Damage | 15 (10 pistol), 33 (guard) |
| Counter | **5 circles** |
| Hazard | Lightning (55 dmg) + meteorite |
| Difficulty | Medium |

### Wave 4 (The Scarlet Ruins)

| Attribute | Value |
|-----------|-------|
| Enemies | 7/7: 1 kiribachi, 2 guard, 2 melee, 1 burn bazooka, 1 pistol |
| HP | 200 each |
| Damage | 15 |
| Counter | **7 circles** |
| Hazard | Lightning + arrows (22 dmg/hit) |
| Difficulty | Medium-Hard |

### Wave 5 (Endure Cupid's Wrath)

| Attribute | Value |
|-----------|-------|
| Enemies | 5 arrow waves (no enemies to kill) |
| Damage | 15/hit |
| Counter | **NO counter** (survival phase) |
| Hazard | Arrows from sky |
| Healing | Player heals |
| Difficulty | Easy (geppo/dash dodge) |

### Wave 6 (Heartguard's Keep)

| Attribute | Value |
|-----------|-------|
| Enemies | 6/6 guards |
| HP | 600 each |
| Damage | 33 |
| Counter | **6 circles** |
| Hazard | Arrow helplessness after clear |
| Difficulty | **HARD** — 6 enemies at 600 HP each = 3600 total HP |

### Wave 7 (Leo's Inferno)

| Attribute | Value |
|-----------|-------|
| Type | Boss fight |
| Boss | Leo (Mera Mera no Mi) |
| HP | 3750 |
| Difficulty | Medium (grounded boss) |
| Drops | Leo's Blazing Regalia, Leo's Blazing Scarf, Inferno Hagoromo |

### Wave 8 (Defeat the Cupid Queen)

| Attribute | Value |
|-----------|-------|
| Type | Final boss (4 stages) |
| HP | 5000 (Stage 1), 2500 (Stage 2), towers 1000 each (Stage 3), continues (Stage 4) |
| Damage | 42 (M1), 72 (R), 35 (E) |
| Stage 3 | 3 towers heal boss — must destroy all |
| Difficulty | **VERY HARD** |
| Drops | Multiple outfits, wings, devil fruit (MVP) |

---

## Finding 8: HSM State Machine Issues

### Current Issues

1. **Counter detection (P0):** Entirely wrong approach — needs rewrite for circle counting
2. **Wave transition:** HSM resets for each wave, but doesn't detect wave number
3. **Stage detection:** Only configured for Wave 1 — `stage_name = "Shattered Ramparts"`
4. **Multi-wave loop:** `CONFIRM_STAGE_TRANSITION` resets to `AGGRO_WITH_GEPPO` — works but naive
5. **No wave number tracking:** Can't distinguish Wave 1 (4/4) from Wave 2 (4/4)

### Recommended HSM Improvements

```
Wave1HSM → DungeonHSM (extended)

ADD:
- _current_wave: int (1-8)
- _counter_threshold: int (per wave: 4, 4, 5, 7, 0, 6, boss, boss)
- _is_survival_wave: bool (Wave 5 = arrows only)
- _is_boss_wave: bool (Wave 7-8)

States to ADD:
- ARROW_DODGE (Wave 5)
- BOSS_DETECT (Wave 7-8)
- TOWER_DESTROY (Cupid Queen Stage 3)
```

---

## Finding 9: Key Differences Between Videos

All 3 videos (539ms, 541ms, 544ms) follow similar patterns:
- Duration: ~58s
- Wave 1 timing: ~2-25s
- Green pixel counts during wave: 551-1300 range
- Compass behavior: consistent

The original video (531ms) was 79.5s — longer run, possibly less optimized build.

---

## Finding 10: Improvement Opportunities

### P0 (Critical — Rewrite Required)

1. **Rewrite `progress_detector.py` counter detection:**
   - Convert crop to grayscale
   - Threshold at brightness=80 to separate filled (bright) from unfilled (dark) circles
   - Connected components on bright regions
   - Filter for circular shapes (aspect ratio 0.5-2.0, area 50-500px)
   - Count filled circles = current kills (0 to counter_total)
   - counter_total = 4 (Wave 1), 4 (Wave 2), 5 (Wave 3), 7 (Wave 4), 0 (Wave 5), 6 (Wave 6)

2. **Add multi-wave support:**
   - Detect wave number from stage name text
   - Set counter threshold per wave
   - Handle survival waves (no counter) vs combat waves

### P1 (High Priority)

3. **Confidence scoring:**
   - Circle detection confidence based on circle shape quality
   - If 4 filled circles detected with high confidence → 4/4 confirmed (no more Radiant Kicks needed)
   - If <4 circles detected → continue combat loop

4. **Green pixel as secondary signal:**
   - Use total green pixel count as confidence multiplier
   - If green count >1000 AND 4 filled circles → very high confidence
   - If green count <200 → low confidence, check again

### P2 (Medium Priority)

5. **Wave 5 survival detection:**
   - No counter (no enemies)
   - Detect arrow phase from compass spike + no counter
   - Auto-dodge with random geppo/dash

6. **Wave 6+ cleanup:**
   - Radiant Kick might not one-shot 6 guards at 600 HP each
   - May need multiple Radiant Kicks or M1+Blitz combo
   - Observation Haki more critical

7. **Lightning/meteorite detection:**
   - Red circle on ground = lightning warning
   - Red circle + growing = meteorite
   - Auto-dodge (geppo/dash) to avoid

8. **Boss detection:**
   - Stage name changes to "Leo" or "Cupid Queen"
   - Different strategy needed (not covered in MVP)

### P3 (Lower Priority)

9. **YOLO enemy detector:**
   - Once counter detection is solid, add enemy type detection
   - Identify katana/bazooka/fist enemy positions
   - Optimize Radiant Kick targeting

10. **RL/PPO fallback:**
    - Symbolic policy fails on later waves
    - Deferred until ≥200 labeled frames

---

## Action Plan Summary

| Priority | Task | File | Effort |
|----------|------|------|--------|
| P0 | Rewrite counter detection (circle counting) | `progress_detector.py` | High |
| P0 | Add multi-wave counter thresholds | `wave1_machine.py` | Medium |
| P1 | Update confidence scoring for circles | `progress_detector.py` | Medium |
| P1 | Verify with real-time test | live run | Low |
| P2 | Wave 5 survival detection | `wave1_machine.py` | Medium |
| P2 | Lightning/meteorite dodge | TBD | High |
| P2 | Boss detection | TBD | High |
| P3 | YOLO enemy detector | TBD | Very High |

---

## Risk Register Update

| Risk | Severity | Old Mitigation | New Mitigation |
|------|----------|----------------|----------------|
| Counter detection fails | CRITICAL | area-based digit estimation | circle fill counting with confidence |
| Wave 2+ detection | HIGH | not planned | per-wave counter threshold |
| Counter < 4 when exiting | CRITICAL | confidence gate | circle count must equal threshold |
| Wave 5 survival phase | MEDIUM | not planned | detect no counter + arrow phase |
| Lightning damage | MEDIUM | not planned | red circle detection + auto-dodge |
| Boss wave automation | LOW | deferred | out of scope for MVP |

---

## Verification Plan

1. **Extract counter crops** from all 3 videos at 2s intervals → `datasets/raw_videos/frames/counter_verify/`
2. **Write HSV + brightness circle detector** in `progress_detector.py`
3. **Test on video timeline** with known ground truth (manual kill count from video)
4. **Verify 0/4 → 4/4 transitions** at t=2-25s window
5. **Test on live gameplay** with assist mode first
6. **Validate on all 3 videos** — consistent circle detection

---

## Crop Reference Images

Saved crops for manual verification:

| File | Content |
|------|---------|
| `counter_verify/counter_t2s.jpg` | Wave 1 start (0 kills) |
| `counter_verify/counter_t10s.jpg` | Wave 1 mid (some kills) |
| `counter_verify/counter_t20s.jpg` | Between waves |
| `counter_verify/green_highlight.jpg` | Green pixel highlight on wave UI |
| `counter_verify/circles_annotated.jpg` | Hough circles on wave panel |
| `counter_deep/crop_t{2,6,10,15,17,22,25}s.jpg` | Zoomed circle row over time |
| `counter_final/zoom_{t}_WAVE_1.jpg` | High-res circle row during wave |
| `video1_ui_search/crop_top_right_700.jpg` | Full wave panel |
| `video1_ui_search/diff_annotation.jpg` | Lobby vs wave diff |

---

*Research completed: 2026-05-09*
*Videos analyzed: MedalTVRoblox20260509053954433-trim, MedalTVRoblox20260509054156446-trim, MedalTVRoblox20260509054405792-trim*
*Wiki: https://grand-piece-online.fandom.com/wiki/Cupid_Dungeon_2026*
*Wiki: https://grand-piece-online.fandom.com/wiki/Pika_Pika_no_Mi/Fruit_Moveset*

---

## Appendix: Pika V2 Moveset (from Wiki, 2026-05-09)

| Key | Move | Stamina | Cooldown | Notes |
|-----|------|---------|---------|-------|
| M1 | Starlight Rapier | 0 | — | Sword combo, scales w/ fruit mastery |
| Q | Starlight Dash | variable | — | 2x distance (HP >70%) |
| E | Blitz Strike | 35 | 13s | Lunge + slam, **stun 1s** |
| R | Radiant Kick | 45 | 13s | Small AoE burst, **blockable** |
| R (Charged) | Radiant Kick Charged | 45 | 13s | **Gold flash → 3 AoE bursts, guard-break** |
| Z | Radiant Ray | 66+ | 18s | Maneuverable ray, 6 explosions |
| T | Radiant Flight | 90 | 15s | Fly + damage |
| X | Radiant Jewels | 78 | 30s | Condensed AoE barrage |
| C | Excalibur | 100 | 70s | Massive line AoE, knock-down |

**Wave 1 combo:** Geppo (Space x5) → Charged R (hold ~1900ms, release on gold flash) → 3 AoE bursts → Guard-break → 4 kills. Fallback: Blitz Strike (E) for stun + cleanup.
