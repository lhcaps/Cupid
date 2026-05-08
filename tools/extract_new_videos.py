#!/usr/bin/env python3
"""Extract and analyze frames from 3 new gameplay videos."""
from __future__ import annotations

import cv2
import os
import numpy as np
from pathlib import Path

VIDEOS = [
    'e:/Macro/Cupid/MedalTVRoblox20260509053954433-trim-1778280259948.mp4',
    'e:/Macro/Cupid/MedalTVRoblox20260509054156446-trim-1778280274477.mp4',
    'e:/Macro/Cupid/MedalTVRoblox20260509054405792-trim-1778280291200.mp4',
]

for video_path in VIDEOS:
    name = Path(video_path).stem
    out_dir = f'e:/Macro/Cupid/datasets/raw_videos/frames/{name}'
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f'ERROR: Cannot open {video_path}')
        continue

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0

    print(f'\n=== {name} ===')
    print(f'FPS: {fps:.2f}, Resolution: {width}x{height}, Frames: {frame_count}, Duration: {duration:.2f}s ({duration/60:.2f}min)')

    # Extract frames every 1 second
    interval_sec = 1.0
    for t in np.arange(0, min(duration + interval_sec, duration + 1), interval_sec):
        frame_num = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            frame_path = f'{out_dir}/frame_{int(t*1000):06d}ms.jpg'
            cv2.imwrite(frame_path, frame)

    # Extract frames every 0.5 seconds for first 20 seconds (wave 1 critical window)
    for t in np.arange(0, min(20.5, duration), 0.5):
        frame_num = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            frame_path = f'{out_dir}/frame_{int(t*1000):06d}ms.jpg'
            cv2.imwrite(frame_path, frame)

    cap.release()
    print(f'Extracted to {out_dir}')
