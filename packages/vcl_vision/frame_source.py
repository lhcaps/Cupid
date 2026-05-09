"""Frame sources: video file and live screen capture."""
from __future__ import annotations

import cv2
import time
import numpy as np
from pathlib import Path
from typing import Iterator

from vcl_core.timebase import Clock
from vcl_core.config import CaptureConfig


class VideoReader:
    """Reads frames from a video file with timestamps."""

    def __init__(self, video_path: str | Path) -> None:
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        self._cap = cv2.VideoCapture(str(self.video_path))
        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open video: {self.video_path}")

        self.fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration_sec = self.frame_count / self.fps if self.fps > 0 else 0.0
        self.clock = Clock()

    def __iter__(self) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (timestamp_sec, frame) tuples using video timestamps."""
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        frame_idx = 0
        while True:
            ret, frame = self._cap.read()
            if not ret:
                break
            yield frame_idx / self.fps, frame.copy()
            frame_idx += 1

    def iter_sampled(self, interval_sec: float = 1.0) -> Iterator[tuple[float, np.ndarray]]:
        """Yield frames at fixed time intervals using video seek."""
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        sample_idx = 0
        while True:
            target_frame = int(sample_idx * interval_sec * self.fps)
            if target_frame >= self.frame_count:
                break
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = self._cap.read()
            if not ret:
                break
            yield sample_idx * interval_sec, frame.copy()
            sample_idx += 1

    def close(self) -> None:
        self._cap.release()

    def __enter__(self) -> "VideoReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def metadata(self) -> dict:
        return {
            "video_path": str(self.video_path),
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "duration_sec": self.duration_sec,
        }


class LiveFrameSource:
    """
    Captures frames from the live screen.

    Supports pluggable backends (MSS default, DXcam for Windows/DirectX).
    Preserves backward-compatible constructor: monitor_index, fps_target, region.
    """

    def __init__(
        self,
        monitor_index: int = 1,
        fps_target: int = 20,
        region: dict | None = None,
        backend: str | None = None,
    ) -> None:
        self._backend_name = backend or "mss"
        self.monitor_index = monitor_index
        self.fps_target = fps_target
        self._interval_sec = 1.0 / fps_target
        self._region = region
        self._running = False
        self.clock = Clock()
        self._stop_flag = False

        from vcl_capture.backends import create_capture_backend
        # Convert dict region to tuple for backend if provided
        backend_region = None
        if self._region is not None:
            # dict format: {"left": x1, "top": y1, "width": w, "height": h}
            r = self._region
            backend_region = (r["left"], r["top"], r["left"] + r["width"], r["top"] + r["height"])
        self._backend = create_capture_backend(
            backend=backend,
            monitor_index=monitor_index,
            region=backend_region,
            output_color="BGR",
        )
        self.width = self._backend.width
        self.height = self._backend.height

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def __iter__(self) -> Iterator[tuple[float, np.ndarray]]:
        self._running = True
        self._stop_flag = False
        self.clock.reset()
        while self._running:
            elapsed = self.clock.now()
            sleep_time = self._interval_sec - elapsed % self._interval_sec
            if sleep_time > 0 and sleep_time < self._interval_sec:
                time.sleep(sleep_time)
            if self._stop_flag:
                break

            frame = self._backend.grab()
            yield self.clock.now(), frame

    def stop(self) -> None:
        self._stop_flag = True
        self._running = False

    def close(self) -> None:
        self._running = False
        self._backend.close()

    def __enter__(self) -> "LiveFrameSource":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
