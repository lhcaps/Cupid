"""Vision debug: save crop snapshots and detector overlays for diagnosis."""
from __future__ import annotations

import json
import time
import cv2
import numpy as np
from pathlib import Path
from dataclasses import asdict

from vcl_core.config import DebugConfig


class VisionDebug:
    """
    Save vision diagnostic data during live runs.

    Writes:
    - reports/vision_debug/<run_id>/
      - frame_<ts>.png         (full frame on state transitions)
      - progress_crop_<ts>.png
      - counter_crop_<ts>.png
      - overlay_<ts>.png       (annotated frame with bounding boxes)
      - debug_<ts>.json        (detector debug info)
    """

    def __init__(self, run_id: str, config: DebugConfig) -> None:
        self.run_id = run_id
        self.config = config
        self._out_dir = Path(config.output_dir) / run_id
        self._frame_count = 0
        self._save_counter = 0

    @property
    def out_dir(self) -> Path:
        return self._out_dir

    def should_save(self) -> bool:
        """True if this frame should be saved based on cadence."""
        if not self.config.vision:
            return False
        self._frame_count += 1
        if self._frame_count % self.config.save_every_n_frames == 0:
            return True
        return False

    def save_overlay(
        self,
        ts: float,
        frame: np.ndarray,
        crop_rects: dict,
    ) -> None:
        """
        Save a full-frame overlay with crop rectangles annotated.

        Args:
            ts: Timestamp in seconds.
            frame: Full capture frame.
            crop_rects: Dict of name -> (x1, y1, x2, y2) rectangles to draw.
                       Colors are auto-assigned from BGR palette.
        """
        if not self.config.vision or frame is None or frame.size == 0:
            return

        self._out_dir.mkdir(parents=True, exist_ok=True)

        overlay = frame.copy()
        colors = [
            (0, 255, 0),    # green
            (255, 0, 0),    # blue
            (0, 165, 255),  # orange
            (128, 0, 128),   # purple
            (0, 255, 255),  # yellow
            (180, 180, 180), # gray
        ]
        for i, (name, rect) in enumerate(crop_rects.items()):
            if rect is None:
                continue
            x1, y1, x2, y2 = rect
            color = colors[i % len(colors)]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                overlay,
                name,
                (x1 + 4, y1 + 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                1,
            )

        cv2.imwrite(str(self._out_dir / f"overlay_{ts:.3f}.png"), overlay)

    def save_frame(
        self,
        ts: float,
        frame: np.ndarray,
        progress_crop: np.ndarray | None = None,
        counter_crop: np.ndarray | None = None,
        overlay: np.ndarray | None = None,
        debug_info: dict | None = None,
    ) -> None:
        """
        Save debug artifacts for this frame.

        Args:
            ts: Timestamp in seconds.
            frame: Full capture frame.
            progress_crop: Cropped progress UI region.
            counter_crop: Cropped counter region.
            overlay: Annotated frame with boxes/overlays.
            debug_info: Detector debug metadata.
        """
        if not self.config.vision:
            return

        self._out_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"frame_{ts:.3f}"

        if frame is not None:
            cv2.imwrite(str(self._out_dir / f"{prefix}.png"), frame)

        if progress_crop is not None and progress_crop.size > 0:
            cv2.imwrite(str(self._out_dir / f"progress_crop_{ts:.3f}.png"), progress_crop)

        if counter_crop is not None and counter_crop.size > 0:
            cv2.imwrite(str(self._out_dir / f"counter_crop_{ts:.3f}.png"), counter_crop)

        if overlay is not None and overlay.size > 0:
            cv2.imwrite(str(self._out_dir / f"overlay_{ts:.3f}.png"), overlay)

        if debug_info:
            dbg_path = self._out_dir / f"debug_{ts:.3f}.json"
            with dbg_path.open("w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": ts,
                    "run_id": self.run_id,
                    **debug_info,
                }, f, indent=2, default=str)

    def save_state_transition(
        self,
        ts: float,
        frame: np.ndarray,
        prev_state: str,
        next_state: str,
        progress_crop: np.ndarray | None = None,
        debug_info: dict | None = None,
    ) -> None:
        """Save debug snapshot on HSM state transitions (always saves, not cadence-gated)."""
        if not self.config.vision:
            return

        self._out_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"transition_{prev_state}_to_{next_state}_{ts:.3f}"

        if frame is not None and frame.size > 0:
            cv2.imwrite(str(self._out_dir / f"{prefix}_frame.png"), frame)

        if progress_crop is not None and progress_crop.size > 0:
            cv2.imwrite(str(self._out_dir / f"{prefix}_progress_crop.png"), progress_crop)

        if debug_info:
            dbg_path = self._out_dir / f"{prefix}_debug.json"
            with dbg_path.open("w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": ts,
                    "run_id": self.run_id,
                    "prev_state": prev_state,
                    "next_state": next_state,
                    **debug_info,
                }, f, indent=2, default=str)
