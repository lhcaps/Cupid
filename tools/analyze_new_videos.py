#!/usr/bin/env python3
"""Deep analysis of 3 new gameplay videos — wave timing, UI patterns, combat behavior."""
from __future__ import annotations

import cv2
import os
import numpy as np
from pathlib import Path

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

for vid_key, video_path, frames_dir in VIDEOS:
    out_dir = f'e:/Macro/Cupid/datasets/raw_videos/frames/{vid_key}_analysis'
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps > 0 else 0
    cap.release()

    print(f'\n{"="*60}')
    print(f'=== {vid_key} ===')
    print(f'Duration: {duration:.2f}s | FPS: {fps:.2f} | Frames: {frame_count}')

    results: list[dict] = []

    for t_ms in range(0, int(duration * 1000), 500):  # every 500ms
        t_sec = t_ms / 1000.0
        frame_path = f'{frames_dir}/frame_{t_ms:06d}ms.jpg'
        if not os.path.exists(frame_path):
            continue

        frame = cv2.imread(frame_path)
        if frame is None:
            continue

        h, w = frame.shape[:2]

        # Analyze progress UI panel
        progress_crop = frame[REGION_PROGRESS['y1']:REGION_PROGRESS['y2'],
                             REGION_PROGRESS['x1']:REGION_PROGRESS['x2']]
        progress_gray = cv2.cvtColor(progress_crop, cv2.COLOR_BGR2GRAY)

        bright_thresholds = {}
        for thresh in [100, 150, 180, 200]:
            _, bright = cv2.threshold(progress_gray, thresh, 255, cv2.THRESH_BINARY)
            bright_thresholds[thresh] = np.sum(bright > 0) / bright.size

        wave_active = bright_thresholds[100] > 0.02

        # Analyze counter area specifically
        counter_crop = frame[REGION_COUNTER['y1']:REGION_COUNTER['y2'],
                            REGION_COUNTER['x1']:REGION_COUNTER['x2']]
        counter_gray = cv2.cvtColor(counter_crop, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(counter_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
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

        # Analyze compass
        compass_crop = frame[REGION_COMPASS['y1']:REGION_COMPASS['y2'],
                            REGION_COMPASS['x1']:REGION_COMPASS['x2']]
        compass_gray = cv2.cvtColor(compass_crop, cv2.COLOR_BGR2GRAY)
        _, bright_compass = cv2.threshold(compass_gray, 180, 255, cv2.THRESH_BINARY)
        num_labels_c, _, stats_c, centroids_c = cv2.connectedComponentsWithStats(bright_compass, connectivity=8)
        compass_blobs = []
        for i in range(1, num_labels_c):
            area = stats_c[i, cv2.CC_STAT_AREA]
            if area > 10:
                cx_c = int(centroids_c[i][0]) + REGION_COMPASS['x1']
                cy_c = int(centroids_c[i][1]) + REGION_COMPASS['y1']
                compass_blobs.append({'x': cx_c, 'area': area})

        result = {
            't_ms': t_ms, 't_sec': round(t_sec, 2),
            'wave_active': wave_active,
            'bright_100': round(bright_thresholds[100], 4),
            'bright_150': round(bright_thresholds[150], 4),
            'blob_count': len(blobs),
            'total_blob_area': round(sum(b['area'] for b in blobs), 1),
            'compass_blobs': len(compass_blobs),
            'compass_pixel_area': round(sum(b['area'] for b in compass_blobs), 1),
        }

        # Save key UI crops
        if t_ms % 2000 == 0:  # every 2s
            cv2.imwrite(f'{out_dir}/progress_t{t_ms:06d}.jpg', progress_crop)
            cv2.imwrite(f'{out_dir}/counter_t{t_ms:06d}.jpg', counter_crop)
            cv2.imwrite(f'{out_dir}/compass_t{t_ms:06d}.jpg', compass_crop)

        results.append(result)

        # Print summary
        status = 'ACTIVE' if wave_active else 'inactive'
        if wave_active:
            print(f'  t={t_sec:5.1f}s | wave={status} | blobs={len(blobs)} | area={result["total_blob_area"]:.0f} | compass={len(compass_blobs)}b')

    # Save results
    import json
    with open(f'{out_dir}/analysis_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Results saved to {out_dir}/analysis_results.json')

print('\n=== Cross-video comparison done ===')
