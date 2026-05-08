#!/usr/bin/env python3
"""Find where the actual wave counter is by scanning entire top screen."""
from __future__ import annotations

import cv2
import os
import numpy as np

VIDEO1 = 'e:/Macro/Cupid/MedalTVRoblox20260509053954433-trim-1778280259948.mp4'
FRAMES_DIR = 'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509053954433-trim-1778280259948'
OUT_DIR = 'e:/Macro/Cupid/datasets/raw_videos/frames/video1_ui_search'
os.makedirs(OUT_DIR, exist_ok=True)

# Get first frame during wave 1
cap = cv2.VideoCapture(VIDEO1)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()

# Read frame at t=6s (middle of wave 1)
frame_path = f'{FRAMES_DIR}/frame_006000ms.jpg'
if not os.path.exists(frame_path):
    frame_path = f'{FRAMES_DIR}/frame_06000ms.jpg'
frame = cv2.imread(frame_path)
if frame is None:
    # Try to find a frame
    for candidate in os.listdir(FRAMES_DIR):
        if candidate.startswith('frame_') and candidate.endswith('.jpg'):
            frame = cv2.imread(f'{FRAMES_DIR}/{candidate}')
            if frame is not None:
                print(f'Using frame: {candidate}')
                break

if frame is None:
    print('No frames found!')
    exit()

h, w = frame.shape[:2]
print(f'Frame: {w}x{h}')

# Scan entire top 300 rows for bright text
print('\n=== Scanning entire top 300 rows for bright text clusters ===')
gray_full = cv2.cvtColor(frame[:300, :], cv2.COLOR_BGR2GRAY)
_, bright = cv2.threshold(gray_full, 180, 255, cv2.THRESH_BINARY)
num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bright, connectivity=8)

text_blobs = []
for i in range(1, num_labels):
    area = stats[i, cv2.CC_STAT_AREA]
    if area < 20:
        continue
    cx = int(centroids[i][0])
    cy = int(centroids[i][1])
    cw_i = stats[i, cv2.CC_STAT_WIDTH]
    ch_i = stats[i, cv2.CC_STAT_HEIGHT]
    aspect = cw_i / max(1, ch_i)
    if aspect < 8:  # Not horizontal bars
        text_blobs.append((cx, cy, cw_i, ch_i, area, aspect))

text_blobs.sort(key=lambda b: b[1])  # Sort by y

print(f'Found {len(text_blobs)} text-like elements in top 300 rows:')
for tb in text_blobs[:40]:
    b, g, r = frame[tb[1], tb[0]]
    print(f'  ({tb[0]:4d}, {tb[1]:3d}) {tb[2]:3d}x{tb[3]:3d} area={tb[4]:5.0f} asp={tb[5]:.2f} RGB({r},{g},{b})')

# Save annotated frame with ALL text-like blobs
ann = frame.copy()
for tb in text_blobs[:40]:
    x, y, cw_i, ch_i = tb[0], tb[1], tb[2], tb[3]
    cv2.rectangle(ann, (x - cw_i//2, y - ch_i//2), (x + cw_i//2, y + ch_i//2), (0, 255, 0), 1)
cv2.imwrite(f'{OUT_DIR}/all_text_blobs.jpg', ann)

# Focus on right side of screen (x > 1000) where wave UI was expected
print('\n=== Text blobs on RIGHT side (x > 800) ===')
right_blobs = [(cx, cy, cw_i, ch_i, area, aspect) for cx, cy, cw_i, ch_i, area, aspect in text_blobs if cx > 800]
for tb in right_blobs[:20]:
    b, g, r = frame[tb[1], tb[0]]
    print(f'  ({tb[0]:4d}, {tb[1]:3d}) {tb[2]:3d}x{tb[3]:3d} area={tb[4]:5.0f} asp={tb[5]:.2f} RGB({r},{g},{b})')

# Also check: maybe the counter is rendered as colored dots/circles, not text
print('\n=== Looking for colored elements (orange/red/gold) ===')
hsv = cv2.cvtColor(frame[:300, 1000:], cv2.COLOR_BGR2HSV)

# Orange/gold (wave progress often uses this color)
lower_orange = np.array([5, 100, 100])
upper_orange = np.array([25, 255, 255])
orange_mask = cv2.inRange(hsv, lower_orange, upper_orange)
orange_count = np.sum(orange_mask > 0)
print(f'Orange pixels in right top area: {orange_count}')

# Red
lower_red = np.array([0, 100, 100])
upper_red = np.array([10, 255, 255])
red_mask = cv2.inRange(hsv, lower_red, upper_red)
red_count = np.sum(red_mask > 0)
print(f'Red pixels in right top area: {red_count}')

# Green (filled circles for progress)
lower_green = np.array([40, 100, 100])
upper_green = np.array([80, 255, 255])
green_mask = cv2.inRange(hsv, lower_green, upper_green)
green_count = np.sum(green_mask > 0)
print(f'Green pixels in right top area: {green_count}')

# Look at specific area around y=100-140 where we expected counter
print('\n=== Detailed pixel scan at y=100-150 ===')
for y in range(100, 155, 5):
    for x in range(1200, 1700, 50):
        b, g, r = frame[y, x]
        if r > 150 or g > 150 or b > 150:  # bright pixel
            pass  # too much output
        else:
            if r < 50 and g < 50 and b < 50:  # very dark pixel
                pass

# Save various crops for manual inspection
print('\n=== Saving crops for inspection ===')
crops = {
    'top_right_500': frame[0:200, 1100:1600],
    'top_right_700': frame[0:200, 900:1600],
    'top_full': frame[0:200, 0:w],
    'top_left_300': frame[0:200, 0:300],
    'y100_160_all': frame[100:160, 0:w],
    'y80_160_1000_1700': frame[80:160, 1000:1700],
    'y100_150_1200_1650': frame[100:150, 1200:1650],
    'y90_160_1100_1800': frame[90:160, 1100:1800],
}
for name, crop in crops.items():
    cv2.imwrite(f'{OUT_DIR}/crop_{name}.jpg', crop)
    print(f'  Saved: crop_{name}.jpg ({crop.shape[1]}x{crop.shape[0]})')

# Also look for circles/dots (potential progress indicators)
print('\n=== Looking for circular elements ===')
gray2 = cv2.cvtColor(frame[0:200, 1000:], cv2.COLOR_BGR2GRAY)
circles = cv2.HoughCircles(gray2, cv2.HOUGH_GRADIENT, 1, 10, param1=50, param2=10, minRadius=3, maxRadius=15)
if circles is not None:
    for circle in circles[0]:
        cx, cy, r = circle
        print(f'  Circle at ({cx+1000:.0f}, {cy:.0f}) radius={r:.1f}')
else:
    print('  No circles found')

# Check what's different between lobby and wave-active frames
print('\n=== Comparing lobby (t=0s) vs wave (t=6s) ===')
lobby_path = f'{FRAMES_DIR}/frame_000000ms.jpg'
wave_path = f'{FRAMES_DIR}/frame_006000ms.jpg'
lobby = cv2.imread(lobby_path) if os.path.exists(lobby_path) else None
wave = cv2.imread(wave_path) if os.path.exists(wave_path) else None

if lobby is not None and wave is not None:
    # Diff the right-top area
    diff = cv2.absdiff(
        lobby[0:200, 1100:1700].astype(np.float32),
        wave[0:200, 1100:1700].astype(np.float32)
    )
    diff_sum = np.sum(diff)
    print(f'  Diff sum (1100-1700, y=0-200): {diff_sum:.0f}')

    # Find where diff is highest
    diff_gray = cv2.cvtColor(diff.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    _, diff_thresh = cv2.threshold(diff_gray, 30, 255, cv2.THRESH_BINARY)
    num_labels_d, _, stats_d, centroids_d = cv2.connectedComponentsWithStats(diff_thresh, connectivity=8)
    diff_blobs = []
    for i in range(1, num_labels_d):
        area = stats_d[i, cv2.CC_STAT_AREA]
        if area > 100:
            cx = int(centroids_d[i][0]) + 1100
            cy = int(centroids_d[i][1])
            diff_blobs.append((cx, cy, area))

    diff_blobs.sort(key=lambda b: b[2], reverse=True)
    print(f'  Top diff regions (lobby vs wave):')
    for db in diff_blobs[:10]:
        print(f'    ({db[0]}, {db[1]}) area={db[2]}')

    # Save annotated diff
    ann2 = wave.copy()
    for db in diff_blobs[:10]:
        cv2.circle(ann2, (db[0], db[1]), 15, (0, 255, 0), 2)
    cv2.imwrite(f'{OUT_DIR}/diff_annotation.jpg', ann2)
    print(f'  Saved diff_annotation.jpg')

print(f'\nAll outputs to {OUT_DIR}')
