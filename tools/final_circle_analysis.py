#!/usr/bin/env python3
"""Final confirmation: zoom into exact circle row and count filled vs unfilled."""
from __future__ import annotations

import cv2
import os
import numpy as np

VIDEO1_DIR = 'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509053954433-trim-1778280259948'
out_dir = 'e:/Macro/Cupid/datasets/raw_videos/frames/counter_final'
os.makedirs(out_dir, exist_ok=True)

print('=== Comparing Lobby vs Wave: Zoomed Circle Row Analysis ===\n')

# The diff showed (1416, 101) as the biggest change
# Let's zoom into x=1350-1600, y=100-130 (where the circles are)

key_frames = [
    (0, 'LOBBY'),
    (500, 'LOBBY'),
    (2000, 'WAVE_1_START'),
    (3000, 'WAVE_1'),
    (5000, 'WAVE_1'),
    (10000, 'WAVE_1'),
    (12000, 'WAVE_1'),
    (26000, 'BETWEEN'),
    (28000, 'BETWEEN'),
]

results = []

for t_ms, label in key_frames:
    frame_path = f'{VIDEO1_DIR}/frame_{t_ms:06d}ms.jpg'
    if not os.path.exists(frame_path):
        continue
    frame = cv2.imread(frame_path)
    if frame is None:
        continue

    # Very zoomed: focus on exact circle row
    zoom = frame[100:135, 1340:1620]  # Very tight around the circle row
    h, w = zoom.shape[:2]

    gray = cv2.cvtColor(zoom, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(zoom, cv2.COLOR_BGR2HSV)
    b, g, r = cv2.split(zoom)
    h_ch, s_ch, v_ch = cv2.split(hsv)

    # Count pixels by category
    dark_pixels = np.sum(gray < 60)
    mid_pixels = np.sum((gray >= 60) & (gray < 120))
    bright_pixels = np.sum(gray >= 120)
    green_pixels = np.sum((g.astype(int) > r.astype(int) * 1.1) & (g.astype(int) > b.astype(int) * 1.1))
    dark_green = np.sum((gray < 60) & (g.astype(int) > r.astype(int) * 1.1) & (g.astype(int) > b.astype(int) * 1.1))

    total = w * h
    dark_pct = dark_pixels / total * 100
    mid_pct = mid_pixels / total * 100
    bright_pct = bright_pixels / total * 100

    # Try to detect circles
    _, thresh = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    inv_thresh = 255 - thresh
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(inv_thresh, connectivity=8)

    circles = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        cx = int(centroids[i][0])
        cy = int(centroids[i][1])
        cw_i = stats[i, cv2.CC_STAT_WIDTH]
        ch_i = stats[i, cv2.CC_STAT_HEIGHT]

        # Filter for circle-ish shapes (aspect ratio close to 1, reasonable area)
        aspect = cw_i / max(1, ch_i)
        if 0.5 < aspect < 2.0 and 50 < area < 500:
            # Check center brightness
            center_y = min(cy, h-1)
            center_x = min(cx, w-1)
            center_bright = gray[center_y, center_x]

            # Check if filled (center is bright) vs unfilled (center is dark)
            filled = center_bright > 80

            circles.append({
                'x': cx, 'y': cy, 'area': area,
                'aspect': aspect,
                'center_bright': center_bright,
                'filled': filled,
            })

    # Count filled vs unfilled
    filled_count = sum(1 for c in circles if c['filled'])
    unfilled_count = len(circles) - filled_count

    result = {
        't_ms': t_ms,
        'label': label,
        'dark_pct': dark_pct,
        'mid_pct': mid_pct,
        'bright_pct': bright_pct,
        'green_pixels': green_pixels,
        'dark_green': dark_green,
        'total_circles': len(circles),
        'filled': filled_count,
        'unfilled': unfilled_count,
    }
    results.append(result)

    print(f't={t_ms/1000:5.1f}s | {label:15} | '
          f'dark={dark_pct:5.1f}% | mid={mid_pct:5.1f}% | bright={bright_pct:5.1f}% | '
          f'green={green_pixels:5d} | circles={len(circles):3d} | '
          f'filled={filled_count:2d} unfilled={unfilled_count:2d}')

    # Save annotated zoom
    ann = zoom.copy()
    for c in circles:
        color = (0, 255, 0) if c['filled'] else (100, 100, 100)
        x, y = c['x'], c['y']
        cv2.circle(ann, (x, y), 8, color, 1)
        cv2.putText(ann, f'{c["center_bright"]}', (x+5, y-3),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.25, (255, 255, 255), 1)

    cv2.imwrite(f'{out_dir}/zoom_{t_ms:06d}_{label}.jpg', zoom)
    cv2.imwrite(f'{out_dir}/ann_{t_ms:06d}_{label}.jpg', ann)

print(f'\nSaved to {out_dir}')

# Now: analyze time series at 250ms intervals to find exact kill moments
print('\n\n=== Time-series at 250ms intervals (0-20s) ===')
print('Looking for green pixel changes that indicate kills...\n')

prev_green = None
prev_filled = None

timestamps_250ms = list(range(0, 20000, 250))
wave_times = []

for t_ms in timestamps_250ms:
    frame_path = f'{VIDEO1_DIR}/frame_{t_ms:06d}ms.jpg'
    if not os.path.exists(frame_path):
        continue
    frame = cv2.imread(frame_path)
    if frame is None:
        continue

    zoom = frame[100:135, 1340:1620]
    gray = cv2.cvtColor(zoom, cv2.COLOR_BGR2GRAY)
    b, g, r = cv2.split(zoom)

    green_pixels = np.sum((g.astype(int) > r.astype(int) * 1.1) & (g.astype(int) > b.astype(int) * 1.1))
    dark_pixels = np.sum(gray < 60)
    total = zoom.shape[0] * zoom.shape[1]

    # Count filled circles
    _, thresh = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    inv_thresh = 255 - thresh
    num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(inv_thresh, connectivity=8)

    filled = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        cx, cy = int(centroids[i][0]), int(centroids[i][1])
        cw_i = stats[i, cv2.CC_STAT_WIDTH]
        ch_i = stats[i, cv2.CC_STAT_HEIGHT]
        aspect = cw_i / max(1, ch_i)
        if 0.5 < aspect < 2.0 and 50 < area < 500:
            center_bright = gray[min(cy, zoom.shape[0]-1), min(cx, zoom.shape[1]-1)]
            if center_bright > 80:
                filled += 1

    t_sec = t_ms / 1000.0

    # Detect transitions
    if prev_green is not None:
        delta_green = green_pixels - prev_green
        delta_filled = filled - prev_filled

        # Significant changes indicate kills or stage transitions
        if abs(delta_green) > 200 or abs(delta_filled) > 1:
            wave_times.append({
                't_sec': t_sec,
                'green': green_pixels,
                'filled': filled,
                'delta_green': delta_green,
                'delta_filled': delta_filled,
            })

    prev_green = green_pixels
    prev_filled = filled

print('Significant transitions (delta green > 200 or delta filled > 1):')
for wt in wave_times:
    direction = 'UP' if wt['delta_green'] > 0 else 'DOWN'
    print(f'  t={wt["t_sec"]:6.2f}s | green={wt["green"]:5d} ({"+" if wt["delta_green"]>0 else ""}{wt["delta_green"]}) | '
          f'filled={wt["filled"]:2d} ({"+" if wt["delta_filled"]>0 else ""}{wt["delta_filled"]}) | {direction}')

print('\n=== Summary ===')
print('If green pixels INCREASE -> enemy killed (circle filled)')
print('If green pixels DECREASE -> wave ended (UI changed)')
print('\nKey insight: Count filled circles = current kill count (0-4)')
