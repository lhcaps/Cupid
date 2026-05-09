"""Find the actual progress UI position in a video frame."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for p in [str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "apps")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2
import numpy as np


def find_progress_ui(frame: np.ndarray, label: str):
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Progress UI has DARK text on semi-transparent bright background
    # Key characteristic: dark pixels clustered in lower-left area
    # Panel BG is ~100-160 gray value

    # Scan the WHOLE frame for dark-on-bright regions
    # The wave panel appears as a cluster of dark pixels
    _, dark = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        dark, connectivity=8
    )

    candidates = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 20 or area > 10000:
            continue

        cx = int(centroids[i][0])
        cy = int(centroids[i][1])
        sx = stats[i, cv2.CC_STAT_LEFT]
        sy = stats[i, cv2.CC_STAT_TOP]
        sw = stats[i, cv2.CC_STAT_WIDTH]
        sh = stats[i, cv2.CC_STAT_HEIGHT]

        # Text-like: taller than wide-ish
        aspect = sw / max(1, sh)
        if aspect > 5.0 or sh < 5:
            continue

        candidates.append({
            "area": area, "cx": cx, "cy": cy,
            "x": sx, "y": sy, "w": sw, "h": sh
        })

    # Sort by area (larger = more text pixels)
    candidates.sort(key=lambda c: -c["area"])

    # Group into rows (y-coordinates)
    # The progress UI text rows should be grouped together
    rows: dict[int, list] = {}
    for c in candidates:
        row_key = round(c["cy"] / 20) * 20
        if row_key not in rows:
            rows[row_key] = []
        rows[row_key].append(c)

    # Find row clusters
    row_groups = []
    for row_y in sorted(rows.keys()):
        regs = rows[row_y]
        x_min = min(r["x"] for r in regs)
        x_max = max(r["x"] + r["w"] for r in regs)
        y_min = min(r["y"] for r in regs)
        y_max = max(r["y"] + r["h"] for r in regs)
        count = len(regs)
        total_area = sum(r["area"] for r in regs)
        row_groups.append({
            "y_center": row_y,
            "x_range": (x_min, x_max),
            "y_range": (y_min, y_max),
            "count": count,
            "total_area": total_area,
        })

    # Filter: look for clusters with multiple text regions (likely UI text)
    # Progress UI: typically 3-8 text rows clustered together
    ui_clusters = []
    for i, rg in enumerate(row_groups):
        if rg["count"] >= 2 and rg["total_area"] >= 100:
            ui_clusters.append(rg)

    print(f"\n=== {label} ({w}x{h}) ===")
    print(f"Top 20 dark regions (sorted by area):")
    for i, c in enumerate(candidates[:20]):
        print(f"  [{i:2d}] area={c['area']:5d} x=[{c['x']:3d},{c['x']+c['w']:3d}] "
              f"y=[{c['y']:3d},{c['y']+c['h']:3d}] cx={c['cx']:3d} cy={c['cy']:3d} "
              f"w={c['w']:2d} h={c['h']:2d}")

    print(f"\nUI clusters (rows with 2+ text regions):")
    for rg in ui_clusters[:10]:
        print(f"  y_center={rg['y_center']:3d} x=[{rg['x_range'][0]:3d},{rg['x_range'][1]:3d}] "
              f"y=[{rg['y_range'][0]:3d},{rg['y_range'][1]:3d}] "
              f"count={rg['count']} area={rg['total_area']}")

    # Look for the progress UI pattern:
    # - "0 / 4" text in lower portion of screen
    # - Multiple rows of dark text in lower-left
    print(f"\nLikely progress UI candidates:")

    # Find clusters in lower half (y > h/2)
    lower_clusters = [rg for rg in ui_clusters if rg["y_center"] > h * 0.5]
    for rg in lower_clusters[:5]:
        print(f"  y_center={rg['y_center']:3d} x=[{rg['x_range'][0]:3d},{rg['x_range'][1]:3d}] "
              f"y=[{rg['y_range'][0]:3d},{rg['y_range'][1]:3d}] "
              f"count={rg['count']} area={rg['total_area']}")

    return ui_clusters, candidates


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--frames", type=str, default="0,300,600,900,1200")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: cannot open {args.video}")
        return

    frame_idx = 0
    target_frames = set(int(x) for x in args.frames.split(","))

    out_dir = Path("reports/ui_finder")
    out_dir.mkdir(parents=True, exist_ok=True)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx in target_frames:
            h, w = frame.shape[:2]
            fps = cap.get(cv2.CAP_PROP_FPS)
            ts = frame_idx / fps

            print(f"\n{'#'*80}")
            print(f"Frame {frame_idx} at t={ts:.1f}s ({w}x{h})")
            print(f"{'#'*80}")

            ui_clusters, candidates = find_progress_ui(frame, f"frame_{frame_idx}")

            # Save annotated frame
            annotated = frame.copy()

            # Draw all dark regions
            for i, c in enumerate(candidates[:30]):
                color = (0, 255, 0) if i < 10 else (100, 255, 100)
                cv2.rectangle(annotated, (c["x"], c["y"]),
                            (c["x"]+c["w"], c["y"]+c["h"]), color, 1)

            # Draw UI clusters
            for rg in ui_clusters[:5]:
                color = (255, 0, 0)
                x1, y1 = rg["x_range"][0], rg["y_range"][0]
                x2, y2 = rg["x_range"][1], rg["y_range"][1]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, f"y={rg['y_center']}", (x1, max(y1-5, 20)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # Also show a grayscale view
            gray_viz = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)

            # Mark the configured crop area
            cfg = None
            try:
                from vcl_core.config import load_config
                cfg = load_config("configs/wave1.local.yaml")
            except:
                pass

            if cfg:
                for name, cr in [
                    ("progress_crop", cfg.progress_ui.crop),
                    ("counter_crop", cfg.progress_ui.counter_crop),
                    ("wave_panel", cfg.progress_ui.wave_panel_crop),
                    ("compass", cfg.compass.crop),
                ]:
                    color = (0, 0, 255)
                    cv2.rectangle(annotated, (cr.x1, cr.y1), (cr.x2, cr.y2), color, 2)
                    cv2.putText(annotated, name, (cr.x1, max(cr.y1-5, 20)),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            out = out_dir / f"frame_{frame_idx:05d}.jpg"
            cv2.imwrite(str(out), annotated)
            print(f"\n  Saved: {out}")

        frame_idx += 1

    cap.release()
    print(f"\n\nAll frames saved to: {out_dir}")


if __name__ == "__main__":
    main()
