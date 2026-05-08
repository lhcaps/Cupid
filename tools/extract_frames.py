#!/usr/bin/env python3
"""Extract frames from video at configurable intervals for manual analysis."""
from __future__ import annotations

import argparse
import cv2
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract frames from video")
    parser.add_argument("--video", required=True, help="Input video path")
    parser.add_argument("--out", default="datasets/frames", help="Output directory")
    parser.add_argument("--every", type=float, default=1.0, help="Extract every N seconds")
    parser.add_argument("--max", type=int, default=0, help="Max frames (0 = all)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"Error: cannot open {args.video}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    interval = int(args.every * fps)
    count = 0
    saved = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if count % interval == 0:
            path = out / f"frame_{saved:06d}.jpg"
            cv2.imwrite(str(path), frame)
            saved += 1
            print(f"  Saved {path} ({saved})")
            if args.max > 0 and saved >= args.max:
                break
        count += 1

    cap.release()
    print(f"\nDone: {saved} frames saved to {out}")


if __name__ == "__main__":
    main()
