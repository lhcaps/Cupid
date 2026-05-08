#!/usr/bin/env python3
"""Deep analysis of 3 new gameplay videos — focus on counter transitions."""
from __future__ import annotations

import cv2
import os
import numpy as np
from pathlib import Path
import json

VIDEOS = [
    ('video1', 'e:/Macro/Cupid/MedalTVRoblox20260509053954433-trim-1778280259948.mp4',
     'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509053954433-trim-1778280259948'),
    ('video2', 'e:/Macro/Cupid/MedalTVRoblox20260509054156446-trim-1778280274477.mp4',
     'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509054156446-trim-1778280274477'),
    ('video3', 'e:/Macro/Cupid/MedalTVRoblox20260509054405792-trim-1778280291200.mp4',
     'e:/Macro/Cupid/datasets/raw_videos/frames/MedalTVRoblox20260509054405792-trim-1778280291200'),
]

# UI regions (2560x1440)
REGION_PROGRESS = {'x1': 1300, 'y1': 0, 'x2': 1850, 'y2': 180}
REGION_COUNTER = {'x1': 1380, 'y1': 110, 'x2': 1620, 'y2': 150}
REGION_COMPASS = {'x1': 1200, 'y1': 10, 'x2': 1400, 'y2': 60}

def analyze_counter(frame):
    """Parse the x/4 counter from a frame."""
    counter_crop = frame[REGION_COUNTER['y1']:REGION_COUNTER['y2'],
                        REGION_COUNTER['x1']:REGION_COUNTER['x2']]
    gray = cv2.cvtColor(counter_crop, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh_val, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    inv = 255 - binary
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(inv, connectivity=8)

    blobs = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 8:
            continue
        cx = int(centroids[i][0])
        cy = int(centroids[i][1])
        cw_i = stats[i, cv2.CC_STAT_WIDTH]
        ch_i = stats[i, cv2.CC_STAT_HEIGHT]
        aspect = cw_i / max(1, ch_i)
        blobs.append({'x': cx, 'y': cy, 'w': cw_i, 'h': ch_i, 'area': area, 'aspect': aspect})

    blobs.sort(key=lambda b: b['x'])

    # Find slash
    slash_idx = None
    for i, blob in enumerate(blobs):
        if blob['aspect'] < 0.5 and blob['area'] < 500:
            slash_idx = i
            break

    if slash_idx is not None and slash_idx > 0 and slash_idx < len(blobs) - 1:
        left_blob = blobs[slash_idx - 1]
        right_blob = blobs[slash_idx + 1]
        left_area = left_blob['area']
        right_area = right_blob['area']

        if 300 < right_area < 1500:
            total = 4
            current = 0
            if left_area > 1200:
                current = 0
            elif left_area > 800:
                current = 2
            elif left_area > 400:
                current = 3
            elif left_area > 200:
                current = 1
            elif left_area > 50:
                current = 4

            return {'current': current, 'total': total, 'confidence': 0.80,
                    'left_area': round(left_area, 1), 'right_area': round(right_area, 1),
                    'blob_count': len(blobs), 'blobs': blobs}

    return {'current': None, 'total': None, 'confidence': 0.0,
            'blob_count': len(blobs), 'blobs': []}


def analyze_progress_panel(frame):
    """Detect wave panel active state."""
    progress_crop = frame[REGION_PROGRESS['y1']:REGION_PROGRESS['y2'],
                         REGION_PROGRESS['x1']:REGION_PROGRESS['x2']]
    gray = cv2.cvtColor(progress_crop, cv2.COLOR_BGR2GRAY)

    bright_counts = {}
    for thresh in [100, 120, 150, 180, 200]:
        _, bright = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
        bright_counts[thresh] = np.sum(bright > 0) / bright.size

    max_ratio = max(bright_counts.values())
    avg_ratio = sum(bright_counts.values()) / len(bright_counts)
    conf = min(1.0, max_ratio * 3 + avg_ratio * 2)
    is_active = max_ratio > 0.02

    return {'active': bool(is_active), 'conf': round(conf, 3), 'max_ratio': round(max_ratio, 4),
            'bright_thresholds': {k: round(v, 4) for k, v in bright_counts.items()}}


def find_counter_transitions(results):
    """Find moments when the counter likely changes."""
    transitions = []
    prev_area = None
    prev_current = None

    for r in results:
        if r['counter']['current'] is not None and prev_current is not None:
            if r['counter']['current'] != prev_current:
                transitions.append({
                    't_sec': r['t_sec'],
                    'from': prev_current,
                    'to': r['counter']['current'],
                    'left_area': r['counter']['left_area'],
                })
        if r['counter']['left_area'] is not None:
            prev_area = r['counter']['left_area']
        if r['counter']['current'] is not None:
            prev_current = r['counter']['current']

    return transitions


for vid_key, video_path, frames_dir in VIDEOS:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0
    cap.release()

    out_dir = f'e:/Macro/Cupid/datasets/raw_videos/frames/{vid_key}_analysis'
    os.makedirs(out_dir, exist_ok=True)

    print(f'\n{"="*70}')
    print(f'=== {vid_key}: {width}x{height}, {fps:.2f}fps, {duration:.2f}s ===')

    results = []

    # Analyze at 0.5s intervals for full duration
    for t_sec in np.arange(0, duration, 0.5):
        t_ms = int(t_sec * 1000)
        frame_path = f'{frames_dir}/frame_{t_ms:06d}ms.jpg'
        if not os.path.exists(frame_path):
            continue

        frame = cv2.imread(frame_path)
        if frame is None:
            continue

        progress = analyze_progress_panel(frame)
        counter = analyze_counter(frame)

        result = {
            't_sec': round(t_sec, 2),
            'progress': progress,
            'counter': counter,
        }
        results.append(result)

        # Print if counter is detected
        if counter['current'] is not None:
            print(f'  t={t_sec:5.1f}s | wave={progress["active"]} | counter={counter["current"]}/4 | '
                  f'conf={counter["confidence"]:.2f} | blobs={counter["blob_count"]} | '
                  f'left_area={counter.get("left_area","-"):>7} | right_area={counter.get("right_area","-"):>7}')

    # Save crops at key moments
    print(f'\n  Saving key frame crops...')
    for r in results:
        if r['t_sec'] < 3 or (25 < r['t_sec'] < 30) or r['t_sec'] > 50:
            t_ms = int(r['t_sec'] * 1000)
            fp = f'{frames_dir}/frame_{t_ms:06d}ms.jpg'
            frame = cv2.imread(fp)
            if frame is not None:
                counter_crop = frame[REGION_COUNTER['y1']:REGION_COUNTER['y2'],
                                    REGION_COUNTER['x1']:REGION_COUNTER['x2']]
                cv2.imwrite(f'{out_dir}/counter_{t_ms:06d}.jpg', counter_crop)

    # Find transitions
    transitions = find_counter_transitions(results)
    print(f'\n  Counter transitions detected: {len(transitions)}')
    for t in transitions:
        print(f'    t={t["t_sec"]:.1f}s: {t["from"]}/4 -> {t["to"]}/4 (left_area={t["left_area"]})')

    # Save full results
    serializable_results = []
    for r in results:
        serializable_results.append({
            't_sec': r['t_sec'],
            'progress': r['progress'],
            'counter': {
                'current': r['counter']['current'],
                'total': r['counter']['total'],
                'confidence': r['counter']['confidence'],
                'left_area': r['counter'].get('left_area'),
                'right_area': r['counter'].get('right_area'),
                'blob_count': r['counter']['blob_count'],
            }
        })

    with open(f'{out_dir}/analysis_results.json', 'w') as f:
        json.dump(serializable_results, f, indent=2)

    print(f'  Saved to {out_dir}/analysis_results.json')

print('\n=== Analysis complete ===')
