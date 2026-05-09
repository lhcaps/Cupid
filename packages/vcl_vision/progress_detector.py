"""Progress UI Detector: supports filled circles (fullscreen) and dark text counter (windowed)."""
from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass

from vcl_core.schemas import ProgressState
from vcl_core.config import ProgressUIConfig


@dataclass
class ProgressDebugInfo:
    """Structured debug info from progress detection."""
    selected_mode: str | None
    circle_count: int | None
    circle_conf: float
    text_count: int | None
    text_conf: float
    panel_active: bool
    panel_conf: float
    candidate_count: int
    raw_confidence: float


class ProgressDetector:
    """
    Detects wave progress from the Cupid progress UI.

    Two counter modes detected automatically:
      - "circle": fullscreen — counter shows filled/empty circles
      - "text":   windowed — counter shows dark text "0/4" on bright panel

    Panel detection: find bright background behind UI (semi-transparent overlay)
    Circle counter: threshold bright regions, count filled circles (bright center)
    Text counter:  threshold dark regions, count digit shapes, infer current/total

    Key insight: counter text is DARK (black/gray pixels), NOT bright.
    Previous approach of thresholding bright pixels was wrong.
    """

    def __init__(self, config: ProgressUIConfig | None = None) -> None:
        self.config = config or ProgressUIConfig()

    def detect(self, frame: np.ndarray) -> ProgressState:
        state, _ = self.detect_with_debug(frame)
        return state

    def detect_with_debug(
        self, frame: np.ndarray
    ) -> tuple[ProgressState, ProgressDebugInfo]:
        h, w = frame.shape[:2]
        cfg = self.config

        x1 = min(cfg.crop.x1, w - 1)
        y1 = min(cfg.crop.y1, h - 1)
        x2 = min(cfg.crop.x2, w)
        y2 = min(cfg.crop.y2, h)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            debug = ProgressDebugInfo(
                selected_mode=None,
                circle_count=None, circle_conf=0.0,
                text_count=None, text_conf=0.0,
                panel_active=False, panel_conf=0.0,
                candidate_count=0,
                raw_confidence=0.0,
            )
            return ProgressState(confidence=0.0), debug

        circle_result = self._count_circles(crop)
        text_result = self._count_text(crop)

        circle_count, circle_conf = circle_result
        text_count, text_conf = text_result

        panel_active_circle, panel_conf_circle = self._detect_panel(crop, mode="circle")
        panel_active_text, panel_conf_text = self._detect_panel(crop, mode="text")

        if circle_count is not None:
            debug = ProgressDebugInfo(
                selected_mode="circle",
                circle_count=circle_count,
                circle_conf=circle_conf,
                text_count=None,
                text_conf=0.0,
                panel_active=panel_active_circle,
                panel_conf=panel_conf_circle,
                candidate_count=candidate_count if (circle_result and len(circle_result) > 2) else 0,
                raw_confidence=0.0,
            )
            if not panel_active_circle:
                debug.raw_confidence = 0.0
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    confidence=0.0,
                ), debug

            raw_conf = round(panel_conf_circle * 0.3 + circle_conf * 0.7, 3)
            debug.raw_confidence = raw_conf
            if raw_conf < cfg.min_confidence:
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    objective_current=circle_count,
                    objective_total=cfg.objective_total,
                    confidence=0.0,
                ), debug
            return ProgressState(
                stage_name=cfg.stage_name,
                dungeon_name=cfg.dungeon_name,
                objective_current=circle_count,
                objective_total=cfg.objective_total,
                confidence=raw_conf,
            ), debug

        if text_count is not None:
            debug = ProgressDebugInfo(
                selected_mode="text",
                circle_count=None, circle_conf=0.0,
                text_count=text_count,
                text_conf=text_conf,
                panel_active=panel_active_text,
                panel_conf=panel_conf_text,
                candidate_count=0,
                raw_confidence=0.0,
            )
            if not panel_active_text:
                debug.raw_confidence = 0.0
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    confidence=0.0,
                ), debug

            raw_conf = round(panel_conf_text * 0.3 + text_conf * 0.7, 3)
            debug.raw_confidence = raw_conf
            if raw_conf < cfg.min_confidence:
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    objective_current=text_count,
                    objective_total=cfg.objective_total,
                    confidence=0.0,
                ), debug
            return ProgressState(
                stage_name=cfg.stage_name,
                dungeon_name=cfg.dungeon_name,
                objective_current=text_count,
                objective_total=cfg.objective_total,
                confidence=raw_conf,
            ), debug

        debug = ProgressDebugInfo(
            selected_mode=None,
            circle_count=None, circle_conf=0.0,
            text_count=None, text_conf=0.0,
            panel_active=False, panel_conf=0.0,
            candidate_count=0,
            raw_confidence=0.0,
        )
        return ProgressState(
            stage_name=cfg.stage_name,
            dungeon_name=cfg.dungeon_name,
            confidence=0.0,
        ), debug

    # ------------------------------------------------------------------
    # Panel active detection
    # ------------------------------------------------------------------

    def _detect_panel(self, crop: np.ndarray, mode: str) -> tuple[bool, float]:
        """
        Detect if progress UI panel is active (visible) in crop.

        For circle mode: look for bright filled circles (background panel)
        For text mode: look for dark text on bright panel background
        """
        if crop.size == 0:
            return False, 0.0

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        if mode == "text":
            _, binary = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY)
            bright_pct = np.sum(binary > 0) / binary.size
            is_active = 0.3 < bright_pct < 0.97
            conf = min(1.0, bright_pct * 1.5) if is_active else 0.0
            return is_active, round(conf, 3)

        else:  # circle mode
            bright_counts = {}
            for thresh in [100, 120, 150, 180, 200]:
                _, bright = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
                bright_counts[thresh] = np.sum(bright > 0) / bright.size

            max_ratio = max(bright_counts.values())
            avg_ratio = sum(bright_counts.values()) / len(bright_counts)
            conf = min(1.0, max_ratio * 3 + avg_ratio * 2)
            is_active = max_ratio > 0.02
            return is_active, round(conf, 3)

    # ------------------------------------------------------------------
    # Circle counter (fullscreen mode)
    # ------------------------------------------------------------------

    def _count_circles(self, crop: np.ndarray) -> tuple[int | None, float]:
        """
        Count filled circles in counter region.
        Filled = bright center (enemy killed), unfilled = dark ring (alive).

        Returns (count, confidence).
        Returns (0, 0.90) ONLY when panel is active AND circle candidates were
        searched but none found. High-confidence 0/4 requires active panel.
        The panel-active check is done at the detect() level, not here.
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

        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
            binary, connectivity=4
        )

        candidates = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 50 or area > 2000:
                continue

            sw = stats[i, cv2.CC_STAT_WIDTH]
            sh = stats[i, cv2.CC_STAT_HEIGHT]
            if sw < 3 or sh < 3:
                continue

            aspect = sw / max(1, sh)
            if not (0.5 <= aspect <= 2.0):
                continue

            candidates.append({"area": area, "w": sw, "h": sh, "aspect": aspect})

        if not candidates:
            return None, 0.0

        count = min(len(candidates), cfg.objective_total)

        avg_area = sum(c["area"] for c in candidates) / len(candidates)
        area_score = min(1.0, avg_area / 150.0)
        count_score = min(1.0, count / cfg.objective_total)
        shape_score = min(
            1.0,
            sum(1.0 - abs(1.0 - c["aspect"]) for c in candidates) / max(1, len(candidates)),
        )
        conf = round(area_score * 0.4 + count_score * 0.3 + shape_score * 0.3, 3)

        return count, conf

    # ------------------------------------------------------------------
    # Text counter (windowed/non-fullscreen mode)
    # ------------------------------------------------------------------

    def _count_text(self, crop: np.ndarray) -> tuple[int | None, float]:
        """
        Count dark text digit shapes in counter region to infer current objective.

        The "0 / 4" counter shows:
          - Dark text on bright panel background
          - Multiple digit shapes separated by slashes/spaces
          - Row y~490 has all digit clusters

        Strategy:
          1. Invert threshold: find DARK pixels (text is black/gray)
          2. Connected components on dark regions
          3. Filter for small compact shapes (digit candidates)
          4. Row-based grouping: top row = numerator, bottom row = denominator
          5. Infer current from numerator digit(s) width
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

        best_result: tuple | None = None

        for text_thresh in [60, 70, 80, 90, 100, 110, 120]:
            _, binary = cv2.threshold(gray, text_thresh, 255, cv2.THRESH_BINARY_INV)

            num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(
                binary, connectivity=8
            )

            digit_candidates = []
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area < 10 or area > 2000:
                    continue

                cx_rel = int(centroids[i][0])
                cy_rel = int(centroids[i][1])
                sw = stats[i, cv2.CC_STAT_WIDTH]
                sh = stats[i, cv2.CC_STAT_HEIGHT]
                if sw < 3 or sh < 5:
                    continue

                aspect = sw / max(1, sh)
                if aspect > 3.0:
                    continue

                digit_candidates.append({
                    "x": cx_rel, "y": cy_rel,
                    "w": sw, "h": sh, "area": area, "aspect": aspect
                })

            if len(digit_candidates) < 2:
                continue

            mid_y = ch / 2
            top_row = [d for d in digit_candidates if d["y"] < mid_y]
            bot_row = [d for d in digit_candidates if d["y"] >= mid_y]

            if not bot_row:
                continue

            top_row.sort(key=lambda d: d["x"])
            bot_row.sort(key=lambda d: d["x"])

            def width_to_digit(w: int, h: int) -> int | None:
                aspect = w / max(1, h)
                if aspect < 0.3:
                    return 1
                if w <= 12:
                    return 1
                if w <= 20:
                    return None
                if w <= 30:
                    return 2
                if w <= 45:
                    return 3
                return 4

            numerator: int | None = None
            if top_row:
                widest_top = max(top_row, key=lambda d: d["w"])
                numerator = width_to_digit(widest_top["w"], widest_top["h"])

            if bot_row:
                widest_bot = max(bot_row, key=lambda d: d["w"])
                bot_digit = width_to_digit(widest_bot["w"], widest_bot["h"])

                if numerator is not None:
                    result_count = numerator
                else:
                    total_w = sum(d["w"] for d in bot_row)
                    if total_w > 50:
                        result_count = 0
                    else:
                        result_count = 0

                total_w_all = sum(d["w"] for d in digit_candidates)
                num_shapes = len(digit_candidates)

                conf = min(1.0, (num_shapes / 6.0) * 0.7 + (total_w_all / 200.0) * 0.3)

                if conf > 0.5:
                    result_count = max(0, min(result_count, cfg.objective_total))
                    if best_result is None or conf > best_result[1]:
                        best_result = (result_count, round(conf, 3))

        if best_result is None:
            return None, 0.0

        return best_result
