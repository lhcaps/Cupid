"""Check compass region in video frame."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for p in [str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "apps")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2
import numpy as np

from vcl_core.config import load_config
from vcl_vision.compass_detector import CompassDetector


def main():
    video_path = "datasets/videos/execute_run1.mp4"
    config_path = "configs/wave1.local.yaml"

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: cannot open {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video: {w}x{h} fps={fps}")

    cfg = load_config(config_path)
    compass_det = CompassDetector(cfg.compass)

    # Analyze multiple frames at different times
    test_frames = [0, 60, 120, 300, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700]

    out_dir = Path("reports/compass_check")
    out_dir.mkdir(parents=True, exist_ok=True)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx in test_frames:
            ts = frame_idx / fps

            # Test current crop
            state = compass_det.detect(frame)

            # Also scan the whole top area for compass-like elements
            gray_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, dark = cv2.threshold(gray_full, 150, 255, cv2.THRESH_BINARY_INV)

            # Find all dark text in top 100 rows
            top_area = dark[0:min(100, h), :]
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                top_area, connectivity=8
            )

            blobs = []
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area < 5:
                    continue
                cx = int(centroids[i][0])
                cy = int(centroids[i][1])
                cw = stats[i, cv2.CC_STAT_WIDTH]
                ch = stats[i, cv2.CC_STAT_HEIGHT]
                blobs.append({
                    "area": area, "cx": cx, "cy": cy,
                    "w": cw, "h": ch, "aspect": cw / max(1, ch)
                })

            blobs.sort(key=lambda b: -b["area"])

            print(f"\nFrame {frame_idx} t={ts:.1f}s: compass={state.label} angle={state.angle_deg} conf={state.confidence:.3f}")
            print(f"  Config crop: [{cfg.compass.crop.x1},{cfg.compass.crop.y1},{cfg.compass.crop.x2},{cfg.compass.crop.y2}]")
            print(f"  Top-100 dark blobs (sorted by area):")
            for b in blobs[:15]:
                print(f"    area={b['area']:4d} x=[{b['cx']-b['w']//2:3d},{b['cx']+b['w']//2:3d}] "
                      f"y=[{b['cy']-b['h']//2:2d},{b['cy']+b['h']//2:2d}] "
                      f"w={b['w']:2d} h={b['h']:2d} aspect={b['aspect']:.2f}")

            # Save annotated frame with crop area
            annotated = frame.copy()

            # Draw crop
            cr = cfg.compass.crop
            cv2.rectangle(annotated, (cr.x1, cr.y1), (cr.x2, cr.y2), (200, 0, 200), 2)
            cv2.putText(annotated, f"compass crop", (cr.x1, max(cr.y1 - 5, 20)),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 0, 200), 1)

            # Draw top blobs
            for b in blobs[:15]:
                x1 = int(b["cx"] - b["w"] // 2)
                y1 = int(b["cy"] - b["h"] // 2)
                x2 = int(b["cx"] + b["w"] // 2)
                y2 = int(b["cy"] + b["h"] // 2)
                color = (0, 255, 0) if b["area"] > 20 else (0, 100, 0)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)

            info = f"Frame {frame_idx} t={ts:.1f}s compass={state.label} conf={state.confidence:.2f}"
            cv2.putText(annotated, info, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            out = out_dir / f"compass_frame_{frame_idx:05d}.jpg"
            cv2.imwrite(str(out), annotated)

        frame_idx += 1

    cap.release()
    print(f"\nSaved to: {out_dir}")


if __name__ == "__main__":
    main()
