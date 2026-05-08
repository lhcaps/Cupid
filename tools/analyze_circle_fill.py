#!/usr/bin/env python3
"""Deep analysis: distinguish filled vs unfilled circles in wave counter."""
from __future__ import annotations

import cv2
import os
import numpy as np

VIDEO1_DIR = 'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509053954433-trim-1778280259948'
out_dir = 'e:/Macro/Cupid/datasets/raw_videos/frames/counter_deep'
os.makedirs(out_dir, exist_ok=True)

# The wave panel is at x=1300-1850, y=0-180
# Counter circles are around y=100-150 based on diff analysis

def analyze_circle_fill(frame):
    """Detect filled vs unfilled circles in the wave counter region."""
    # Crop the counter region where circles are visible
    # Diff showed (1416, 101) as biggest change - this is the circle row
    crop = frame[90:160, 1250:1700]
    h, w = crop.shape[:2]

    # Convert to different color spaces
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    # Split channels
    b, g, r = cv2.split(crop)

    # Strategy 1: Green channel dominance (filled circles are green/bright)
    # The circles are about 15-20px radius, spaced horizontally

    # Find dark circles (unfilled) - dark pixels with circular shape
    _, dark_thresh = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)
    # Remove noise
    kernel = np.ones((3, 3), np.uint8)
    dark_clean = cv2.morphologyEx(dark_thresh, cv2.MORPH_OPEN, kernel)

    # Find bright circles (filled) - bright pixels
    _, bright_thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)

    # Count connected components in each
    num_dark, _, _, _, _ = cv2.connectedComponentsWithStats(dark_clean, connectivity=8)
    num_bright, _, _, _, _ = cv2.connectedComponentsWithStats(bright_thresh, connectivity=8)

    # Look for circular shapes using Hough Circles on each channel
    circles_gray = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, 15, param1=40, param2=8, minRadius=5, maxRadius=15)
    circles_green = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, 1, 15, param1=30, param2=8, minRadius=5, maxRadius=15)
    circles_dark = cv2.HoughCircles(dark_thresh, cv2.HOUGH_GRADIENT, 1, 15, param1=30, param2=8, minRadius=5, maxRadius=15)

    # Analyze green vs non-green in potential circle locations
    # If a circle area is predominantly green -> filled
    # If predominantly dark -> unfilled

    results = {
        'dark_components': num_dark - 1,  # subtract background
        'bright_components': num_bright - 1,
        'circles_gray': len(circles_gray[0]) if circles_gray is not None else 0,
        'circles_green': len(circles_green[0]) if circles_green is not None else 0,
        'circles_dark': len(circles_dark[0]) if circles_dark is not None else 0,
    }

    # Save annotated crop
    ann = crop.copy()
    if circles_green is not None:
        for circle in circles_green[0]:
            cx, cy, r_c = circle
            cv2.circle(ann, (int(cx), int(cy)), int(r_c), (0, 255, 0), 1)
            # Check center pixel color
            ix, iy = int(cx), int(cy)
            if 0 <= iy < h and 0 <= ix < w:
                pb, pg, pr = ann[iy, ix]
                cv2.putText(ann, f'({pg})', (ix+5, iy), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

    return results, ann


def find_circle_row(frame):
    """Find the horizontal row where the counter circles are."""
    crop = frame[90:160, 1250:1700]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Scan each row for circular patterns
    circle_row_scores = {}
    for y in range(0, 70, 5):
        row = gray[y:y+15, :]
        _, thresh = cv2.threshold(row, 100, 255, cv2.THRESH_BINARY)

        # Look for circular patterns in this row
        # A circle will have a specific intensity pattern
        circles = cv2.HoughCircles(row, cv2.HOUGH_GRADIENT, 1, 20,
                                   param1=30, param2=5, minRadius=5, maxRadius=12)
        if circles is not None:
            score = len(circles[0])
            circle_row_scores[y] = score

    return circle_row_scores


print('=== Time-series circle analysis (0-25s, every 1s) ===\n')

# Analyze frames from t=0 to t=25s
timestamps = list(range(0, 25000, 500))

all_results = []

for t_ms in timestamps:
    frame_path = f'{VIDEO1_DIR}/frame_{t_ms:06d}ms.jpg'
    if not os.path.exists(frame_path):
        continue

    frame = cv2.imread(frame_path)
    if frame is None:
        continue

    t_sec = t_ms / 1000.0

    # Get green pixel count in counter region
    crop = frame[90:160, 1250:1700]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lower_g = np.array([40, 50, 50])
    upper_g = np.array([90, 255, 255])
    green_mask = cv2.inRange(hsv, lower_g, upper_g)
    green_count = np.sum(green_mask > 0)

    # Get gray values
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Count circular elements
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, 15,
                               param1=50, param2=8, minRadius=5, maxRadius=15)

    # Find filled circles (bright center)
    if circles is not None:
        filled = 0
        unfilled = 0
        circle_data = []

        for circle in circles[0]:
            cx, cy, r_c = circle
            ix, iy = int(cx), int(cy)

            # Sample center and edge of circle
            center_brightness = gray[iy, ix] if (0 <= iy < crop.shape[0] and 0 <= ix < crop.shape[1]) else 0

            # Check if center is brighter than surrounding (filled)
            if center_brightness > 80:
                filled += 1
            else:
                unfilled += 1

            circle_data.append((ix, iy, int(r_c), center_brightness))

        all_results.append({
            't_sec': t_sec,
            'green': green_count,
            'total_circles': len(circles[0]),
            'filled': filled,
            'unfilled': unfilled,
            'circle_data': circle_data[:5],  # first 5 for debugging
        })

        # Print summary
        status = 'WAVE' if green_count > 100 else 'LOBBY'
        if filled > 0 or unfilled > 0:
            print(f'  t={t_sec:5.1f}s | {status:6} | green={green_count:4d} | circles={len(circles[0]):3d} | '
                  f'filled={filled:2d} unfilled={unfilled:2d} | '
                  f'center_brightness={circle_data[0][3] if circle_data else "-"}')
    else:
        all_results.append({
            't_sec': t_sec,
            'green': green_count,
            'total_circles': 0,
            'filled': 0,
            'unfilled': 0,
        })
        print(f'  t={t_sec:5.1f}s | NO_CIRCLES | green={green_count}')

    # Save crops at key moments
    if t_sec in [0, 2, 6, 10, 15, 17, 22, 25]:
        cv2.imwrite(f'{out_dir}/crop_t{t_sec:.0f}s.jpg', crop)

        # Save annotated version
        ann = crop.copy()
        if circles is not None:
            for ix, iy, r_c, bright in circle_data[:8]:
                color = (0, 255, 0) if bright > 80 else (128, 128, 128)
                cv2.circle(ann, (ix, iy), r_c, color, 1)
                cv2.putText(ann, f'{bright}', (ix+5, iy), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)
        cv2.imwrite(f'{out_dir}/annotated_t{t_sec:.0f}s.jpg', ann)

print(f'\nSaved to {out_dir}')

# Now analyze a zoomed-in circle region
print('\n\n=== Zoomed circle analysis ===')
frame = cv2.imread(f'{VIDEO1_DIR}/frame_006000ms.jpg')
if frame is not None:
    # Very zoomed crop focused on where circles should be
    zoom = frame[95:145, 1280:1600]
    cv2.imwrite(f'{out_dir}/zoom_t6s.jpg', zoom)

    # Analyze pixel distribution
    gray_zoom = cv2.cvtColor(zoom, cv2.COLOR_BGR2GRAY)
    hsv_zoom = cv2.cvtColor(zoom, cv2.COLOR_BGR2HSV)

    print(f'Zoomed area shape: {zoom.shape}')
    print(f'Gray: min={gray_zoom.min()}, max={gray_zoom.max()}, mean={gray_zoom.mean():.1f}')

    # HSV channels
    h, s, v = cv2.split(hsv_zoom)
    print(f'H: min={h.min()}, max={h.max()}, mean={h.mean():.1f}')
    print(f'S: min={s.min()}, max={s.max()}, mean={s.mean():.1f}')
    print(f'V: min={v.min()}, max={v.max()}, mean={v.mean():.1f}')

    # Count pixels by brightness band
    for lo, hi, label in [(0, 30, 'very_dark'), (30, 80, 'dark'), (80, 150, 'mid'), (150, 220, 'bright'), (220, 256, 'very_bright')]:
        mask = (gray_zoom >= lo) & (gray_zoom < hi)
        count = np.sum(mask)
        print(f'  {label} ({lo}-{hi}): {count} pixels ({100*count/(zoom.shape[0]*zoom.shape[1]):.1f}%)')

    # Try color segmentation: separate filled from unfilled
    # Filled circles should have high green or high brightness
    # Unfilled should be dark

    # Method: threshold on grayscale + green dominance
    _, thresh = cv2.threshold(gray_zoom, 80, 255, cv2.THRESH_BINARY)
    inv_thresh = cv2.bitwise_not(thresh)

    filled_blobs = cv2.connectedComponentsWithStats(inv_thresh, connectivity=8)
    print(f'\nBright regions (potential filled circles): {filled_blobs[0]-1} components')

    # Dark blobs
    dark_blobs = cv2.connectedComponentsWithStats(thresh, connectivity=8)
    print(f'Dark regions (potential unfilled circles): {dark_blobs[0]-1} components')

    # Save
    cv2.imwrite(f'{out_dir}/zoom_annotated_t6s.jpg', zoom)
