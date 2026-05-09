#!/usr/bin/env python3
"""
Collect YOLO training frames from live capture.

Usage:
    python tools/collect_yolo_frames.py --out datasets/yolo_raw/run1 --duration-sec 60 --fps 10
    python tools/collect_yolo_frames.py --out datasets/yolo_raw/run2 --backend dxcam --monitor-index 1

No HSM/input import. No game automation. Just captures frames + metadata.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import typer
import cv2
import numpy as np

app = typer.Typer(help="Collect raw frames for YOLO training dataset.")


@app.command()
def collect(
    out: Path = typer.Option(Path("datasets/yolo_raw/default"), "--out", "-o",
                              help="Output directory"),
    duration_sec: float = typer.Option(60.0, "--duration-sec", "-d",
                                       help="Capture duration in seconds"),
    fps: int = typer.Option(10, "--fps", "-f", help="Capture FPS"),
    backend: str = typer.Option("mss", "--backend", "-b",
                                 help="Capture backend: mss (default) or dxcam"),
    monitor_index: int = typer.Option(1, "--monitor-index", "-m",
                                      help="Monitor index (1 = primary)"),
    region: str = typer.Option("", "--region",
                               help="Region as x1,y1,x2,y2 (optional)"),
) -> None:
    """Capture frames from live screen into a directory for YOLO annotation."""
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)

    capture_backend = _create_capture_backend(backend, monitor_index, region)
    print(f"[INFO] Backend: {capture_backend.name}")
    print(f"[INFO] Resolution: {capture_backend.width}x{capture_backend.height}")
    print(f"[INFO] FPS target: {fps}")
    print(f"[INFO] Duration: {duration_sec}s")
    print(f"[INFO] Output: {out_dir}")
    print(f"[INFO] Starting capture... (Ctrl+C to stop early)")

    interval_sec = 1.0 / fps
    start_time = time.monotonic()
    frame_count = 0
    metadata = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_sec": duration_sec,
        "fps": fps,
        "backend": capture_backend.name,
        "monitor_index": monitor_index,
        "region": region or None,
        "width": capture_backend.width,
        "height": capture_backend.height,
        "frames": [],
    }

    try:
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= duration_sec:
                break

            sleep_time = interval_sec - (time.monotonic() - start_time) % interval_sec
            if sleep_time > 0:
                time.sleep(sleep_time)

            frame = capture_backend.grab()
            ts = time.monotonic() - start_time
            filename = f"frame_{frame_count:06d}_{ts:.3f}s.png"
            filepath = images_dir / filename
            cv2.imwrite(str(filepath), frame)

            metadata["frames"].append({
                "filename": filename,
                "timestamp_sec": round(ts, 3),
                "frame_index": frame_count,
            })
            frame_count += 1

            if frame_count % fps == 0:
                print(f"  [{elapsed:.1f}s] Captured {frame_count} frames...")

    except KeyboardInterrupt:
        print(f"\n[INFO] Interrupted at {time.monotonic() - start_time:.1f}s")

    capture_backend.close()

    metadata["total_frames"] = frame_count
    metadata_path = out_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n[OK] Collected {frame_count} frames -> {out_dir}")


def _create_capture_backend(
    backend: str,
    monitor_index: int,
    region_str: str,
):
    region = None
    if region_str:
        try:
            parts = [int(x.strip()) for x in region_str.split(",")]
            if len(parts) == 4:
                region = {"left": parts[0], "top": parts[1],
                          "width": parts[2] - parts[0], "height": parts[3] - parts[1]}
        except ValueError:
            pass

    name = backend.lower().strip()
    if name == "mss":
        import mss
        sct = mss.MSS()
        m = sct.monitors[monitor_index]
        width, height = m["width"], m["height"]

        class MSSSimple:
            name = "mss"
            width = width
            height = height

            def grab(self):
                shot = sct.grab(region or m)
                return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

            def close(self):
                sct.close()

        return MSSSimple()

    if name == "dxcam":
        try:
            dxcam = __import__("dxcam", fromlist=["DXCam"])
            cam = dxcam.DXCam()
            info = cam.get_monitors_info()
            if info:
                target = info[min(monitor_index, len(info) - 1)]
                width = int(target.get("width", 1920))
                height = int(target.get("height", 1080))
            else:
                width, height = 1920, 1080

            class DXCamSimple:
                name = "dxcam"
                width = width
                height = height

                def grab(self):
                    frame = cam.grab()
                    if frame is None:
                        raise RuntimeError("DXcam grab returned None")
                    return frame

                def close(self):
                    cam.release()

            return DXCamSimple()
        except ImportError:
            raise RuntimeError(
                "dxcam not installed. Install with: pip install dxcam"
            )

    raise ValueError(f"Unknown backend: {backend!r}. Use 'mss' or 'dxcam'.")


if __name__ == "__main__":
    app()
