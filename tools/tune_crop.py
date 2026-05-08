#!/usr/bin/env python3
"""Tune crop regions interactively — shows live crop preview on screen."""
from __future__ import annotations

import cv2
import argparse
import numpy as np
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune crop regions interactively")
    parser.add_argument("--video", help="Video path (optional, uses first if omitted)")
    parser.add_argument("--frame", type=int, default=0, help="Frame number to use")
    args = parser.parse_args()

    cap = None
    video_path = args.video
    if video_path:
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)

    window = "Crop Tuner"
    cv2.namedWindow(window)

    x1, y1, x2, y2 = 0, 0, 560, 190

    def nothing(_):
        pass

    cv2.createTrackbar("x1", window, x1, 2560, lambda v: _update(0, v))
    cv2.createTrackbar("y1", window, y1, 1440, lambda v: _update(1, v))
    cv2.createTrackbar("x2", window, x2, 2560, lambda v: _update(2, v))
    cv2.createTrackbar("y2", window, y2, 1440, lambda v: _update(3, v))

    def _update(idx, val):
        nonlocal x1, y1, x2, y2
        [x1, y1, x2, y2][idx] = val

    while True:
        if cap:
            ret, frame = cap.read()
            if not ret:
                break
        else:
            print("No video provided. Use --video to specify a source.")
            break

        h, w = frame.shape[:2]
        x1 = min(x1, w - 1)
        y1 = min(y1, h - 1)
        x2 = min(x2, w)
        y2 = min(y2, h)

        crop = frame[y1:y2, x1:x2]
        if crop.size > 0:
            cv2.imshow("Crop Preview", crop)

        display = frame.copy()
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(display, f"Crop: [{x1}, {y1}, {x2}, {y2}]", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(window, display)

        key = cv2.waitKey(30)
        if key == 27 or key == ord('q'):
            break

    if cap:
        cap.release()
    cv2.destroyAllWindows()

    print(f"\nFinal crop: [{x1}, {y1}, {x2}, {y2}]")
    print(f"Size: {x2 - x1}x{y2 - y1}")


if __name__ == "__main__":
    main()
