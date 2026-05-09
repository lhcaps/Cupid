"""Pluggable capture backends: MSS and DXcam."""
from __future__ import annotations

import abc
import numpy as np

from vcl_core.config import CaptureConfig


class CaptureBackend(abc.ABC):
    """Abstract capture backend interface."""

    name: str = "abstract"
    width: int = 0
    height: int = 0

    @abc.abstractmethod
    def grab(self) -> np.ndarray:
        """Capture a frame. Returns BGR numpy array."""
        ...

    @abc.abstractmethod
    def close(self) -> None:
        """Release backend resources."""
        ...


class MSSCaptureBackend(CaptureBackend):
    """MSS-based screen capture. Always available as fallback."""

    name = "mss"

    def __init__(
        self,
        monitor_index: int = 1,
        region: dict | None = None,
    ) -> None:
        import mss
        self._sct = mss.MSS()
        self._region = region
        self._monitor = self._sct.monitors[monitor_index]
        self.width = self._monitor["width"]
        self.height = self._monitor["height"]

    def grab(self) -> np.ndarray:
        import cv2
        shot = self._sct.grab(self._region or self._monitor)
        frame = np.array(shot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    def close(self) -> None:
        self._sct.close()


class DXCamCaptureBackend(CaptureBackend):
    """
    DXcam-based screen capture using Windows Desktop Duplication API.
    Low-latency, high-FPS, ideal for full-screen Direct3D applications.

    Requires: pip install "dxcam[cv2,winrt]"
    """

    name = "dxcam"

    def __init__(
        self,
        monitor_index: int = 1,
        region: tuple[int, int, int, int] | None = None,
        output_color: str = "BGR",
        fps_target: int = 20,
    ) -> None:
        dxcam = __import__("dxcam", fromlist=["create"])
        self._cam = dxcam.create(
            output_idx=max(0, monitor_index - 1),
            output_color=output_color,
            region=region,
        )
        self._output_color = output_color
        self._fps_target = fps_target

        self.width = getattr(self._cam, "width", 1920)
        self.height = getattr(self._cam, "height", 1080)

    def grab(self) -> np.ndarray:
        frame = self._cam.get_latest_frame()
        if frame is None:
            raise RuntimeError(
                "DXcam grab() returned None. "
                "Ensure Roblox window is visible and not minimized."
            )
        return frame

    def close(self) -> None:
        self._cam.release()


def create_capture_backend(
    backend: str | None = None,
    monitor_index: int = 1,
    region: tuple[int, int, int, int] | None = None,
    output_color: str = "BGR",
    fps_target: int = 20,
) -> CaptureBackend:
    """
    Factory: create a CaptureBackend by name.

    Args:
        backend: "mss" (default fallback) or "dxcam" (Windows/DirectX).
        monitor_index: Monitor to capture (1 = primary).
        region: Optional (x1, y1, x2, y2) crop.
        output_color: "BGR" (default) or "RGB".
        fps_target: Target FPS (used for timing in the frame source).

    Returns:
        A CaptureBackend instance.
    """
    name = (backend or "mss").lower().strip()

    if name == "mss":
        return MSSCaptureBackend(
            monitor_index=monitor_index,
            region=_region_to_dict(region),
        )

    if name == "dxcam":
        try:
            return DXCamCaptureBackend(
                monitor_index=monitor_index,
                region=region,
                output_color=output_color,
                fps_target=fps_target,
            )
        except (ImportError, ModuleNotFoundError) as exc:
            if "dxcam" in str(exc):
                raise RuntimeError(
                    "DXcam backend selected but dxcam is not installed. "
                    "Install with: pip install \"dxcam[cv2,winrt]\""
                ) from None
            raise

    raise ValueError(f"Unknown capture backend: {backend!r}. Use 'mss' or 'dxcam'.")


def _region_to_dict(region: tuple[int, int, int, int] | None) -> dict | None:
    """Convert (x1,y1,x2,y2) tuple to MSS monitor dict."""
    if region is None:
        return None
    return {
        "left": region[0],
        "top": region[1],
        "width": region[2] - region[0],
        "height": region[3] - region[1],
    }
