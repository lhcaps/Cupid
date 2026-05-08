#!/usr/bin/env python3
"""Verify green circle counter theory — analyze cropped frames for circle patterns."""
from __future__ import annotations

import cv2
import os
import numpy as np

# Analyze the crops we saved
SEARCH_DIR = 'e:/Macro/Cupid/datasets/raw_videos/frames/video1_ui_search'
COUNTER_CROP = 'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509053954433-trim-1778280259948'

out_dir = 'e:/Macro/Cupid/datasets/raw_videos/frames/counter_verify'
os.makedirs(out_dir, exist_ok=True)

# Load the top-right crop
top_right = cv2.imread(f'{SEARCH_DIR}/crop_y100_150_1200_1650.jpg')
if top_right is None:
    top_right = cv2.imread(f'{SEARCH_DIR}/crop_y90_160_1100_1800.jpg')

if top_right is not None:
    print(f'Crop shape: {top_right.shape}')
    h, w = top_right.shape[:2]
    print(f'Size: {w}x{h}')

    # Analyze HSV in this crop
    hsv = cv2.cvtColor(top_right, cv2.COLOR_BGR2HSV)

    # Check for green (filled progress circles)
    lower_green = np.array([40, 50, 50])
    upper_green = np.array([90, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # Check for dark (empty/unfilled circles)
    gray = cv2.cvtColor(top_right, cv2.COLOR_BGR2GRAY)
    _, dark_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)

    # Check for white/bright (active counter text)
    _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    print(f'\nPixel counts in counter crop ({w}x{h}):')
    print(f'  Green pixels: {np.sum(green_mask > 0)} ({100*np.sum(green_mask>0)/(w*h):.1f}%)')
    print(f'  Dark pixels: {np.sum(dark_mask > 0)} ({100*np.sum(dark_mask>0)/(w*h):.1f}%)')
    print(f'  Bright pixels: {np.sum(bright_mask > 0)} ({100*np.sum(bright_mask>0)/(w*h):.1f}%)')

    # Save annotated version
    ann = top_right.copy()
    ann[green_mask > 0] = [0, 255, 0]  # highlight green
    cv2.imwrite(f'{out_dir}/green_highlight.jpg', ann)

# Now load the full top-right area and do Hough circles
print('\n=== Hough Circles on full top-right wave area ===')
wave_crop = cv2.imread(f'{SEARCH_DIR}/crop_top_right_700.jpg')
if wave_crop is not None:
    h2, w2 = wave_crop.shape[:2]
    gray2 = cv2.cvtColor(wave_crop, cv2.COLOR_BGR2GRAY)

    # Try different parameters
    for dp in [1, 2]:
        for minDist in [10, 20, 30]:
            circles = cv2.HoughCircles(
                gray2, cv2.HOUGH_GRADIENT, dp, minDist,
                param1=50, param2=10, minRadius=5, maxRadius=20
            )
            if circles is not None:
                unique_y = set()
                for circle in circles[0]:
                    cx, cy, r = circle
                    unique_y.add(int(cy))
                print(f'  dp={dp}, minDist={minDist}: {len(circles[0])} circles, unique y rows: {sorted(unique_y)}')

    # Best attempt with green channel
    b, g, r = cv2.split(wave_crop)
    green_only = g

    circles = cv2.HoughCircles(
        green_only, cv2.HOUGH_GRADIENT, 1, 15,
        param1=30, param2=8, minRadius=3, maxRadius=20
    )

    if circles is not None:
        print(f'\nGreen channel circles: {len(circles[0])}')
        # Group by y position
        y_groups = {}
        for circle in circles[0]:
            cx, cy, rad = circle
            y_bucket = int(cy // 10) * 10
            if y_bucket not in y_groups:
                y_groups[y_bucket] = []
            y_groups[y_bucket].append((int(cx), int(cy), int(rad)))

        for y in sorted(y_groups.keys()):
            circles_in_row = y_groups[y]
            x_positions = [c[0] for c in circles_in_row]
            radii = [c[2] for c in circles_in_row]
            print(f'  y={y}: {len(circles_in_row)} circles at x={x_positions}, radii={radii}')

        # Draw on image
        ann2 = wave_crop.copy()
        for circle in circles[0]:
            cx, cy, rad = circle
            cv2.circle(ann2, (int(cx), int(cy)), int(rad), (0, 255, 0), 1)
        cv2.imwrite(f'{out_dir}/circles_annotated.jpg', ann2)
        print(f'  Saved circles_annotated.jpg')

# Look at time-series: how does the counter area change over time?
print('\n=== Time-series analysis: counter region over 30s ===')
timestamps_to_check = list(range(0, 30000, 1000))  # every 1s for 30s

prev_green_count = None
transitions = []

for t_ms in timestamps_to_check:
    frame_path = f'{COUNTER_CROP}/frame_{t_ms:06d}ms.jpg'
    if not os.path.exists(frame_path):
        continue

    frame = cv2.imread(frame_path)
    if frame is None:
        continue

    # Crop counter region
    counter = frame[100:150, 1300:1650]
    hsv_c = cv2.cvtColor(counter, cv2.COLOR_BGR2HSV)

    # Count green pixels
    lower_g = np.array([40, 50, 50])
    upper_g = np.array([90, 255, 255])
    green_m = cv2.inRange(hsv_c, lower_g, upper_g)
    green_count = np.sum(green_m > 0)

    # Count dark pixels (potential empty circles)
    gray_c = cv2.cvtColor(counter, cv2.COLOR_BGR2GRAY)
    _, dark_m = cv2.threshold(gray_c, 80, 255, cv2.THRESH_BINARY_INV)
    dark_count = np.sum(dark_m > 0)

    t_sec = t_ms / 1000.0
    print(f'  t={t_sec:5.1f}s: green={green_count:5d}, dark={dark_count:5d}')

    if prev_green_count is not None:
        diff = green_count - prev_green_count
        if abs(diff) > 100:  # significant change
            transitions.append((t_sec, prev_green_count, green_count, diff))

    prev_green_count = green_count

print(f'\nSignificant transitions:')
for t, before, after, diff in transitions:
    direction = 'INCREASE' if diff > 0 else 'DECREASE'
    print(f'  t={t:.1f}s: {before} -> {after} ({direction} by {abs(diff)})')

# Save crops at key timestamps
print(f'\nSaving counter crops at key timestamps to {out_dir}/...')
for t_ms in [2000, 4000, 6000, 8000, 10000, 15000, 20000, 25000]:
    frame_path = f'{COUNTER_CROP}/frame_{t_ms:06d}ms.jpg'
    if os.path.exists(frame_path):
        frame = cv2.imread(frame_path)
        crop = frame[90:160, 1250:1700]
        cv2.imwrite(f'{out_dir}/counter_t{t_ms//1000}s.jpg', crop)

print(f'\nAll verification outputs to {out_dir}')
