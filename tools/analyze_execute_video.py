"""Comprehensive video analysis for execute run debugging."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for p in [str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "apps")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2
import numpy as np

from vcl_core.config import load_config, AppConfig, CropRegion
from vcl_vision.progress_detector import ProgressDetector
from vcl_vision.compass_detector import CompassDetector


def analyze_video(video_path: str, config_path: str):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: cannot open {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0

    print(f"Video: {width}x{height}, fps={fps:.1f}, frames={frame_count}, duration={duration:.1f}s")

    cfg = load_config(config_path)
    pcfg = cfg.progress_ui
    ccfg = cfg.compass

    progress_det = ProgressDetector(pcfg)
    compass_det = CompassDetector(ccfg)

    out_dir = Path("reports/video_analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Config crops (for reference)
    print(f"\nConfig crops:")
    print(f"  progress_ui.crop:         {pcfg.crop.x1},{pcfg.crop.y1},{pcfg.crop.x2},{pcfg.crop.y2}")
    print(f"  progress_ui.counter_crop:  {pcfg.counter_crop.x1},{pcfg.counter_crop.y1},{pcfg.counter_crop.x2},{pcfg.counter_crop.y2}")
    print(f"  progress_ui.wave_panel:    {pcfg.wave_panel_crop.x1},{pcfg.wave_panel_crop.y1},{pcfg.wave_panel_crop.x2},{pcfg.wave_panel_crop.y2}")
    print(f"  compass.crop:              {ccfg.crop.x1},{ccfg.crop.y1},{ccfg.crop.x2},{ccfg.crop.y2}")

    # Frame analysis
    total_frames = frame_count
    report: list[dict] = []

    # Sample every 30 frames for overview, plus key frames
    sample_step = max(1, total_frames // 100)

    print(f"\nSampling every {sample_step} frames...")

    frame_idx = 0
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_step != 0 and frame_idx > 60:
            frame_idx += 1
            continue

        ts = frame_idx / fps

        # Get detections
        pstate = progress_det.detect(frame)
        cstate = compass_det.detect(frame)

        # Pixel analysis of crops
        px_analysis = {}
        for name, crop_r in [
            ("progress_crop", pcfg.crop),
            ("counter_crop", pcfg.counter_crop),
            ("wave_panel", pcfg.wave_panel_crop),
            ("compass_crop", ccfg.crop),
        ]:
            x1, y1 = max(0, crop_r.x1), max(0, crop_r.y1)
            x2, y2 = min(width, crop_r.x2), min(height, crop_r.y2)
            if x2 <= x1 or y2 <= y1:
                px_analysis[name] = "INVALID_CROP"
                continue
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                px_analysis[name] = "EMPTY"
                continue
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            px_analysis[name] = f"min={gray.min()},max={gray.max()},mean={gray.mean():.1f}"

        report.append({
            "frame": frame_idx, "ts": ts,
            "obj": f"{pstate.objective_current}/{pstate.objective_total}" if pstate.objective_current is not None else "?",
            "pconf": f"{pstate.confidence:.2f}",
            "compass": cstate.label if cstate.label else "?",
            "ccomp": f"{cstate.confidence:.2f}",
            "panel": px_analysis.get("progress_crop", "?"),
            "counter": px_analysis.get("counter_crop", "?"),
        })

        frame_idx += 1

    cap.release()

    # Print summary table
    print(f"\n{'='*100}")
    print(f"{'FRAME':>6} {'TIME':>6} {'OBJ':>5} {'PCONF':>6} {'COMPASS':>7} {'CCONF':>6} {'progress_crop':>30}")
    print(f"{'='*100}")
    for r in report:
        print(f"{r['frame']:>6} {r['ts']:>5.1f}s {r['obj']:>5} {r['pconf']:>6} {r['compass']:>7} {r['ccomp']:>6}  {r['panel']}")

    print(f"\n{'='*100}")
    print("Counter ROI analysis:")
    for r in report:
        print(f"  frame={r['frame']:>4} ts={r['ts']:>5.1f}s {r['obj']:>5} pconf={r['pconf']:>6}  counter: {r['counter']}")

    print(f"\n{'='*100}")
    print("Compass ROI analysis:")
    for r in report:
        print(f"  frame={r['frame']:>4} ts={r['ts']:>5.1f}s compass={r['compass']:>7} cconf={r['ccomp']:>6}")

    # Extract key frames as images
    print(f"\nExtracting key frames...")
    cap2 = cv2.VideoCapture(video_path)
    frame_idx = 0
    key_frames = list(range(0, min(300, total_frames), 30)) + \
                 list(range(300, min(600, total_frames), 60)) + \
                 [total_frames // 4, total_frames // 2, total_frames * 3 // 4]
    key_frames = sorted(set(key_frames))

    while True:
        ret, frame = cap2.read()
        if not ret:
            break
        if frame_idx in key_frames:
            ts = frame_idx / fps
            annotated = frame.copy()

            # Draw config crops
            colors = [(0, 255, 0), (255, 0, 0), (0, 200, 255), (200, 0, 200)]
            labels = ["crop", "counter", "wave_panel", "compass"]
            crops = [pcfg.crop, pcfg.counter_crop, pcfg.wave_panel_crop, ccfg.crop]

            for label, cr, color in zip(labels, crops, colors):
                x1 = max(0, cr.x1)
                y1 = max(0, cr.y1)
                x2 = min(width, cr.x2)
                y2 = min(height, cr.y2)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, label, (x1, max(y1 - 5, 20)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # Detect on this frame
            ps = progress_det.detect(frame)
            cs = compass_det.detect(frame)

            info = f"F={frame_idx} t={ts:.1f}s obj={ps.objective_current}/{ps.objective_total} conf={ps.confidence:.2f} compass={cs.label} cconf={cs.confidence:.2f}"
            cv2.putText(annotated, info, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            out = out_dir / f"frame_{frame_idx:05d}_t{ts:.1f}s.jpg"
            cv2.imwrite(str(out), annotated)
            print(f"  Saved: {out}")

        frame_idx += 1

    cap2.release()
    print(f"\nAll frames saved to: {out_dir}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--config", type=str, default="configs/wave1.local.yaml")
    args = parser.parse_args()

    analyze_video(args.video, args.config)
