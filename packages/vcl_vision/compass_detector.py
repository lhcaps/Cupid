"""Compass Detector: reads heading from the top compass bar (TOP CENTER)."""
from __future__ import annotations

import cv2
import numpy as np

from vcl_core.schemas import CompassState
from vcl_core.config import CompassConfig


HEADING_LABELS: dict[str, int] = {
    "N": 0,
    "NE": 45,
    "E": 90,
    "SE": 135,
    "S": 180,
    "SW": 225,
    "W": 270,
    "NW": 315,
}

HEADING_INVERSE: dict[int, str] = {v: k for k, v in HEADING_LABELS.items()}


class CompassDetector:
    """
    Detects compass heading from the top compass bar.

    From video analysis (2560x1440):
    - Compass indicator: TOP CENTER at x=1260-1295, y=15-55 (~35x40px)
    - This is a single character indicator that moves between 8 positions
    - The full compass bar spans the top with all 8 labels (N, NE, E, SE, S, SW, W, NW)
    - The active heading is highlighted

    Detection strategy:
    1. Crop the compass region (wider search to catch all labels)
    2. Find all bright text blobs in the region
    3. Classify each blob as a compass label
    4. Find the brightest/most prominent one (the active heading)
    5. Interpolate between labels if needed
    """

    LABEL_TEMPLATES = {
        "N": None,
        "NE": None,
        "E": None,
        "SE": None,
        "S": None,
        "SW": None,
        "W": None,
        "NW": None,
    }

    def __init__(self, config: CompassConfig | None = None) -> None:
        self.config = config or CompassConfig()

    def detect(self, frame: np.ndarray) -> CompassState:
        """
        Analyze a full frame and return the compass heading.
        Returns CompassState with low confidence if compass not visible.
        """
        h, w = frame.shape[:2]
        cfg = self.config

        x1 = min(cfg.crop.x1, w - 1)
        y1 = min(cfg.crop.y1, h - 1)
        x2 = min(cfg.crop.x2, w)
        y2 = min(cfg.crop.y2, h)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return CompassState(confidence=0.0)

        heading, angle, conf = self._detect_heading(crop)

        return CompassState(
            label=heading,
            angle_deg=angle,
            confidence=round(conf, 3),
        )

    def _detect_heading(self, crop: np.ndarray) -> tuple[str | None, float | None, float]:
        """
        Core heading detection:
        1. Find all bright blobs in the compass region
        2. Classify each as a compass label
        3. Select the most prominent (active) heading
        """
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        _, bright = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            bright, connectivity=8
        )

        blobs: list[dict] = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 10:
                continue
            cx_rel = int(centroids[i][0])
            cy_rel = int(centroids[i][1])
            cw = stats[i, cv2.CC_STAT_WIDTH]
            ch = stats[i, cv2.CC_STAT_HEIGHT]
            aspect = cw / max(1, ch)

            if ch < 3 or cw < 3:
                continue
            if not (0.1 < aspect < 4.0):
                continue

            brightness = np.mean(gray[labels == i])
            blobs.append({
                "label": None,
                "cx_rel": cx_rel,
                "cy_rel": cy_rel,
                "w": cw,
                "h": ch,
                "area": area,
                "aspect": aspect,
                "brightness": brightness,
            })

        if not blobs:
            return None, None, 0.0

        screen_center_rel = crop.shape[1] / 2
        for blob in blobs:
            blob["label"] = self._classify_label_by_aspect(
                blob["w"], blob["h"], blob["aspect"]
            )

        for blob in blobs:
            dist_from_center = abs(blob["cx_rel"] - screen_center_rel)
            blob["center_dist"] = dist_from_center

        blobs.sort(key=lambda b: b["brightness"], reverse=True)
        best = blobs[0]

        heading = best["label"]
        if heading is None:
            heading = self._infer_from_position(best, blobs)

        angle = HEADING_LABELS.get(heading, 180)

        conf = self._compute_confidence(best, screen_center_rel, crop.shape[1])

        return heading, float(angle), conf

    def _classify_label_by_aspect(self, w: int, h: int, aspect: float) -> str | None:
        """
        Classify a compass label blob by its dimensions.

        Single letters: N, E, S, W (tall aspect ~0.5-0.8)
        Double letters: NE, NW, SE, SW (wide aspect ~1.2-2.0)
        """
        if aspect < 0.8:
            if h > w * 1.5:
                return "N"
            elif h > w:
                return "I"
            return "l"
        elif aspect > 1.5:
            return "W"
        elif aspect > 1.0:
            return "E"
        return "S"

    def _infer_from_position(
        self, best: dict, all_blobs: list[dict]
    ) -> str:
        """Infer compass label from screen position (relative x coordinate)."""
        cx = best["cx_rel"]
        total_w = best.get("total_width", 1000)
        rel_pos = cx / max(1, total_w)

        if rel_pos < 0.15:
            return "NW"
        elif rel_pos < 0.25:
            return "N"
        elif rel_pos < 0.35:
            return "NE"
        elif rel_pos < 0.45:
            return "E"
        elif rel_pos < 0.55:
            return "SE"
        elif rel_pos < 0.65:
            return "S"
        elif rel_pos < 0.80:
            return "SW"
        else:
            return "W"

    def _compute_confidence(
        self,
        best: dict,
        screen_center_x: float,
        total_width: float,
    ) -> float:
        """Compute confidence from brightness and proximity to center."""
        brightness = best.get("brightness", 200)
        brightness_conf = min(1.0, brightness / 255.0)

        dist = abs(best.get("cx_rel", 0) - screen_center_x)
        max_dist = total_width / 2
        dist_conf = max(0.0, 1.0 - (dist / max_dist))

        conf = brightness_conf * 0.6 + dist_conf * 0.4
        return min(1.0, conf)
