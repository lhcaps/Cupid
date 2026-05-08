"""Progress UI Detector: parses wave panel and objective counter from top-right UI."""
from __future__ import annotations

import re
import cv2
import numpy as np
from typing import Literal

from vcl_core.schemas import ProgressState
from vcl_core.config import ProgressUIConfig


class ProgressDetector:
    """
    Detects wave progress and objective counter from the top-right UI panel.

    From real video analysis (2560x1440):
    - Wave panel is a dark semi-transparent overlay at TOP-RIGHT
    - Counter "x/4" appears within or just below the wave panel
    - The wave panel has specific pixel patterns: wave_bright_ratio ~0.22 when active
    - Counter is dark text rendered on dark background

    Detection strategy:
    1. Detect wave panel: crop top-right, check for active wave pattern (bright ratio > threshold)
    2. Parse counter: find the "x/4" pattern within the wave panel using inverted thresholding
    3. Never fake a 4/4 state — require high confidence
    """

    def __init__(self, config: ProgressUIConfig | None = None) -> None:
        self.config = config or ProgressUIConfig()

    def detect(self, frame: np.ndarray) -> ProgressState:
        """
        Analyze a full frame and return the progress state.
        Returns ProgressState with low confidence if no wave is active.
        """
        h, w = frame.shape[:2]
        cfg = self.config

        x1 = min(cfg.crop.x1, w - 1)
        y1 = min(cfg.crop.y1, h - 1)
        x2 = min(cfg.crop.x2, w)
        y2 = min(cfg.crop.y2, h)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return ProgressState(confidence=0.0)

        panel_active, panel_conf = self._detect_wave_active(crop)
        if not panel_active:
            return ProgressState(confidence=0.0)

        counter_data = self._parse_wave_counter(crop)
        current = counter_data.get("current")
        total = counter_data.get("total")
        counter_conf = counter_data.get("confidence", 0.0)

        overall_conf = panel_conf * 0.3 + counter_conf * 0.7

        if (current == 4 and total == 4) and overall_conf < cfg.min_confidence:
            return ProgressState(
                stage_name=cfg.stage_name,
                confidence=0.0,
            )

        return ProgressState(
            stage_name=cfg.stage_name,
            dungeon_name=cfg.dungeon_name,
            objective_current=current,
            objective_total=total,
            confidence=round(overall_conf, 3),
        )

    def _detect_wave_active(self, crop: np.ndarray) -> tuple[bool, float]:
        """
        Detect if the wave panel is active (visible) in the crop.

        The wave panel shows ~22% bright pixels when active, 0% when inactive.
        Uses multiple thresholds to handle different UI rendering modes.
        """
        cfg = self.config

        # Crop the wave panel region
        panel_x = cfg.wave_panel_crop.x1 - cfg.crop.x1
        panel_y = cfg.wave_panel_crop.y1 - cfg.crop.y1
        panel_w = cfg.wave_panel_crop.x2 - cfg.wave_panel_crop.x1
        panel_h = cfg.wave_panel_crop.y2 - cfg.wave_panel_crop.y1

        panel_x = max(0, panel_x)
        panel_y = max(0, panel_y)
        panel_x2 = min(panel_x + panel_w, crop.shape[1])
        panel_y2 = min(panel_y + panel_h, crop.shape[0])

        if panel_x2 <= panel_x or panel_y2 <= panel_y:
            return False, 0.0

        panel_crop = crop[panel_y:panel_y2, panel_x:panel_x2]
        if panel_crop.size == 0:
            return False, 0.0

        gray = cv2.cvtColor(panel_crop, cv2.COLOR_BGR2GRAY)

        # Check bright pixels with multiple thresholds
        bright_counts = {}
        for thresh in [100, 120, 150, 180, 200]:
            _, bright = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
            bright_counts[thresh] = np.sum(bright > 0) / bright.size

        max_ratio = max(bright_counts.values())
        avg_ratio = sum(bright_counts.values()) / len(bright_counts)

        conf = min(1.0, max_ratio * 3 + avg_ratio * 2)

        is_active = max_ratio > 0.02

        return is_active, round(conf, 3)

    def _parse_wave_counter(self, crop: np.ndarray) -> dict:
        """
        Parse the "x/4" counter from the wave panel.

        The counter is rendered as dark text within the wave panel overlay.
        Strategy: invert the crop and find the digit-like blobs.
        The left digit (x) and right digit (4) are separated by a slash.
        """
        cfg = self.config

        # Counter crop region
        counter_x = cfg.counter_crop.x1 - cfg.crop.x1
        counter_y = cfg.counter_crop.y1 - cfg.crop.y1
        counter_w = cfg.counter_crop.x2 - cfg.counter_crop.x1
        counter_h = cfg.counter_crop.y2 - cfg.counter_crop.y1

        counter_x = max(0, counter_x)
        counter_y = max(0, counter_y)
        counter_x2 = min(counter_x + counter_w, crop.shape[1])
        counter_y2 = min(counter_y + counter_h, crop.shape[0])
        cw = counter_x2 - counter_x
        ch = counter_y2 - counter_y

        if cw <= 0 or ch <= 0:
            return {"found": False, "current": None, "total": None, "confidence": 0.0}

        counter_crop = crop[counter_y:counter_y2, counter_x:counter_x2]
        if counter_crop.size == 0:
            return {"found": False, "current": None, "total": None, "confidence": 0.0}

        gray = cv2.cvtColor(counter_crop, cv2.COLOR_BGR2GRAY)

        # The counter text is DARK on DARK background
        # Use adaptive threshold to find text vs background
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh_val, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        inv = 255 - binary

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(inv, connectivity=8)

        blobs: list[dict] = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 8:
                continue
            cx = int(centroids[i][0])
            cy = int(centroids[i][1])
            cw_i = stats[i, cv2.CC_STAT_WIDTH]
            ch_i = stats[i, cv2.CC_STAT_HEIGHT]
            aspect = cw_i / max(1, ch_i)

            blobs.append({
                "x": cx, "y": cy,
                "w": cw_i, "h": ch_i,
                "area": area,
                "aspect": aspect,
            })

        blobs.sort(key=lambda b: b["x"])

        if len(blobs) < 2:
            return {"found": False, "current": None, "total": None, "confidence": 0.0}

        # Find the slash "/" between two digits
        # The slash is a narrow vertical blob (aspect < 0.5)
        current = None
        total = None
        slash_idx = None

        for i, blob in enumerate(blobs):
            if blob["aspect"] < 0.5 and blob["area"] < 500:
                slash_idx = i
                break

        if slash_idx is not None and slash_idx > 0 and slash_idx < len(blobs) - 1:
            left_blob = blobs[slash_idx - 1]
            right_blob = blobs[slash_idx + 1]

            left_area = left_blob["area"]
            right_area = right_blob["area"]

            # Estimate digit from area
            # "0" is widest (area ~1500-2000)
            # "4" is medium (area ~600-1000)
            # "1" is narrow (area ~200-400)
            # "2", "3" are medium (area ~400-1500)

            # Heuristic: left blob is the current count, right blob is total (always 4)
            # Total (4) is consistent: right blob should have area ~600-1200
            if 300 < right_area < 1500:
                total = 4
                current = self._estimate_digit(left_area, left_blob["aspect"])

            if total is not None and current is not None:
                return {
                    "found": True,
                    "current": current,
                    "total": total,
                    "confidence": 0.80,
                }

        # Fallback: use area ratio between left and right halves
        mid_x = cw // 2
        left_area = sum(b["area"] for b in blobs if b["x"] < mid_x)
        right_area = sum(b["area"] for b in blobs if b["x"] >= mid_x)

        if left_area > 0 and right_area > 0:
            ratio = left_area / right_area
            if 1.0 < ratio < 3.5:
                return {
                    "found": True,
                    "current": 0,
                    "total": 4,
                    "confidence": 0.60,
                }
            elif ratio >= 3.5:
                return {
                    "found": True,
                    "current": 1,
                    "total": 4,
                    "confidence": 0.55,
                }

        return {"found": False, "current": None, "total": None, "confidence": 0.0}

    def _estimate_digit(self, area: float, aspect: float) -> int | None:
        """Estimate which digit (0-4) based on blob area."""
        if aspect < 0.5:
            return None  # This is a slash, not a digit

        # Based on pixel analysis from real video:
        # Large blob (~1500 area) = "0"
        # Small blob (~200-400 area) = "1"
        # Medium blob (~600-1200 area) = "4" (or 2, 3)
        if area > 1200:
            return 0
        elif area > 800:
            return 2
        elif area > 400:
            return 3
        elif area > 200:
            return 1
        elif area > 50:
            return 4

        return None
