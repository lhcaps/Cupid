"""Progress UI Detector: parses wave panel and filled-circle counter from top-right UI."""
from __future__ import annotations

import cv2
import numpy as np

from vcl_core.schemas import ProgressState
from vcl_core.config import ProgressUIConfig


class ProgressDetector:
    """
    Detects wave progress and objective counter from the top-right UI panel.

    From real video analysis (2560x1440):
    - Wave panel is a dark semi-transparent overlay at TOP-RIGHT
    - Counter renders as FILLED CIRCLES (not text "x/4")
    - Filled circle (bright center) = enemy killed
    - Unfilled circle (dark ring) = enemy alive
    - Counter region: y=100-135, x=1340-1620 (TOP-RIGHT)
    - Wave panel region: x=1300-1850, y=0-180

    Detection strategy:
    1. Detect wave panel: crop top-right, check for active wave pattern
    2. Count filled circles: threshold bright regions, connected components,
       filter for circular shapes (area 50-500px, aspect ratio 0.5-2.0)
    3. Never fake 4/4 on low confidence
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

        circle_count, circle_conf = self._count_filled_circles(crop)

        if circle_count is None:
            return ProgressState(
                stage_name=cfg.stage_name,
                dungeon_name=cfg.dungeon_name,
                confidence=0.0,
            )

        objective_current = circle_count
        objective_total = cfg.objective_total

        overall_conf = round(panel_conf * 0.3 + circle_conf * 0.7, 3)

        if objective_current == objective_total and overall_conf < cfg.min_confidence:
            return ProgressState(
                stage_name=cfg.stage_name,
                dungeon_name=cfg.dungeon_name,
                confidence=0.0,
            )

        return ProgressState(
            stage_name=cfg.stage_name,
            dungeon_name=cfg.dungeon_name,
            objective_current=objective_current,
            objective_total=objective_total,
            confidence=overall_conf,
        )

    def _detect_wave_active(self, crop: np.ndarray) -> tuple[bool, float]:
        """
        Detect if the wave panel is active (visible) in the crop.

        The wave panel shows ~22% bright pixels when active, 0% when inactive.
        Uses multiple thresholds to handle different UI rendering modes.
        """
        cfg = self.config

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

        bright_counts = {}
        for thresh in [100, 120, 150, 180, 200]:
            _, bright = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
            bright_counts[thresh] = np.sum(bright > 0) / bright.size

        max_ratio = max(bright_counts.values())
        avg_ratio = sum(bright_counts.values()) / len(bright_counts)

        conf = min(1.0, max_ratio * 3 + avg_ratio * 2)

        is_active = max_ratio > 0.02

        return is_active, round(conf, 3)

    def _count_filled_circles(self, crop: np.ndarray) -> tuple[int | None, float]:
        """
        Count filled circles in the counter region.

        Filled circle (enemy killed): bright center, grayscale >80
        Unfilled circle (enemy alive): dark ring, grayscale <60

        Strategy:
        1. Crop counter region
        2. Grayscale + threshold at brightness=80
        3. Connected components on bright regions
        4. Filter for circular shapes: area 50-500px, aspect ratio 0.5-2.0
        5. Count filled circles = objective_current
        """
        cfg = self.config

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
            return None, 0.0

        counter_crop = crop[counter_y:counter_y2, counter_x:counter_x2]
        if counter_crop.size == 0:
            return None, 0.0

        gray = cv2.cvtColor(counter_crop, cv2.COLOR_BGR2GRAY)

        _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            binary, connectivity=4
        )

        candidates: list[dict] = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 50 or area > 500:
                continue

            cx_rel = int(centroids[i][0])
            cy_rel = int(centroids[i][1])
            cw_i = stats[i, cv2.CC_STAT_WIDTH]
            ch_i = stats[i, cv2.CC_STAT_HEIGHT]

            if cw_i < 3 or ch_i < 3:
                continue

            aspect = cw_i / max(1, ch_i)
            if not (0.5 <= aspect <= 2.0):
                continue

            candidates.append({
                "x": cx_rel,
                "y": cy_rel,
                "w": cw_i,
                "h": ch_i,
                "area": area,
                "aspect": aspect,
            })

        filled_count = len(candidates)

        if filled_count == 0:
            return 0, 0.0

        avg_area = sum(c["area"] for c in candidates) / len(candidates)
        area_score = min(1.0, avg_area / 150.0)
        count_score = min(1.0, filled_count / cfg.objective_total)
        shape_score = min(
            1.0,
            sum(1.0 - abs(1.0 - c["aspect"]) for c in candidates) / max(1, len(candidates)),
        )

        conf = round(area_score * 0.4 + count_score * 0.3 + shape_score * 0.3, 3)

        return filled_count, conf
