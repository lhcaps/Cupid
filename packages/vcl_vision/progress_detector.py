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
    slot_count: int        # empty ring/slot candidates (for 0/4 detection)
    slot_conf: float      # confidence of slot ring detection (circularity-based)
    raw_confidence: float   # computed confidence before min-confidence gate
    accepted_confidence: float = 0.0  # confidence that passed min-confidence gate (0.0 if rejected)


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
                slot_count=0,
                slot_conf=0.0,
                raw_confidence=0.0,
            )
            return ProgressState(confidence=0.0), debug

        text_result = self._count_text(crop)
        circle_result = self._count_circles(crop)

        circle_count, circle_conf, candidate_count, slot_count, slot_conf = circle_result
        text_count, text_conf = text_result

        panel_active_circle, panel_conf_circle = self._detect_panel(crop, mode="circle")
        panel_active_text, panel_conf_text = self._detect_panel(crop, mode="text")

        # Text counters are made of bright glyphs ("0 / 4") and can otherwise be
        # mistaken for circle blobs. Prefer a structured text read when present.
        if text_count is not None and text_conf >= 0.65:
            panel_conf_text = max(panel_conf_text, min(1.0, text_conf))
            panel_active_text = panel_active_text or panel_conf_text >= 0.65
            debug = ProgressDebugInfo(
                selected_mode="text",
                circle_count=None, circle_conf=0.0,
                text_count=text_count,
                text_conf=text_conf,
                panel_active=panel_active_text,
                panel_conf=panel_conf_text,
                candidate_count=0,
                slot_count=0,
                slot_conf=0.0,
                raw_confidence=0.0,
                accepted_confidence=0.0,
            )
            if not panel_active_text:
                debug.raw_confidence = 0.0
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    confidence=0.0,
                ), debug

            raw_conf = round(panel_conf_text * 0.2 + text_conf * 0.8, 3)
            debug.raw_confidence = raw_conf
            if raw_conf < cfg.min_confidence:
                debug.accepted_confidence = 0.0
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    objective_current=text_count,
                    objective_total=cfg.objective_total,
                    confidence=0.0,
                ), debug
            debug.accepted_confidence = raw_conf
            return ProgressState(
                stage_name=cfg.stage_name,
                dungeon_name=cfg.dungeon_name,
                objective_current=text_count,
                objective_total=cfg.objective_total,
                confidence=raw_conf,
            ), debug

        if circle_count is not None or slot_count > 0:
            # Build debug info — raw_confidence and accepted_confidence set below
            debug = ProgressDebugInfo(
                selected_mode="circle",
                circle_count=circle_count,
                circle_conf=circle_conf,
                text_count=None,
                text_conf=0.0,
                panel_active=panel_active_circle,
                panel_conf=panel_conf_circle,
                candidate_count=candidate_count,
                slot_count=slot_count,
                slot_conf=slot_conf,
                raw_confidence=0.0,
                accepted_confidence=0.0,
            )

            if not panel_active_circle:
                debug.raw_confidence = 0.0
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    confidence=0.0,
                ), debug

            # 0/4 case: no filled circles but visible slot rings
            if circle_count == 0 and slot_count >= cfg.objective_total:
                raw_conf = round(panel_conf_circle * 0.25 + slot_conf * 0.75, 3)
                debug.raw_confidence = raw_conf
                debug.accepted_confidence = raw_conf  # 0/4 uses slot_conf directly
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    objective_current=0,
                    objective_total=cfg.objective_total,
                    confidence=raw_conf,
                ), debug

            if circle_count is not None:
                raw_conf = round(panel_conf_circle * 0.3 + circle_conf * 0.7, 3)
                debug.raw_confidence = raw_conf
                if raw_conf < cfg.min_confidence:
                    debug.accepted_confidence = 0.0
                    return ProgressState(
                        stage_name=cfg.stage_name,
                        dungeon_name=cfg.dungeon_name,
                        objective_current=circle_count,
                        objective_total=cfg.objective_total,
                        confidence=0.0,
                    ), debug
                debug.accepted_confidence = raw_conf
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    objective_current=circle_count,
                    objective_total=cfg.objective_total,
                    confidence=raw_conf,
                ), debug

            # circle_count is None and slot_count == 0: no detection
            debug.raw_confidence = 0.0
            return ProgressState(
                stage_name=cfg.stage_name,
                dungeon_name=cfg.dungeon_name,
                confidence=0.0,
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
                slot_count=0,
                slot_conf=0.0,
                raw_confidence=0.0,
                accepted_confidence=0.0,
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
                debug.accepted_confidence = 0.0
                return ProgressState(
                    stage_name=cfg.stage_name,
                    dungeon_name=cfg.dungeon_name,
                    objective_current=text_count,
                    objective_total=cfg.objective_total,
                    confidence=0.0,
                ), debug
            debug.accepted_confidence = raw_conf
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
            slot_count=0,
            slot_conf=0.0,
            raw_confidence=0.0,
            accepted_confidence=0.0,
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
            _, bright = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)
            num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
                bright, connectivity=8
            )
            text_like = 0
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                width = stats[i, cv2.CC_STAT_WIDTH]
                height = stats[i, cv2.CC_STAT_HEIGHT]
                if 8 <= area <= 2500 and width >= 2 and height >= 4:
                    text_like += 1
            conf = min(1.0, text_like / 8.0)
            return conf >= 0.35, round(conf, 3)

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

    def _count_empty_slots(
        self,
        gray_or_crop: np.ndarray,
        cw: int | None = None,
        ch: int | None = None,
    ) -> tuple[int, float]:
        """
        Detect empty unfilled slot rings in the counter region.

        Unfilled slots appear as DARK rings (dark circle outlines, unfilled interior)
        at the expected circle positions. We detect them by looking for donut-like
        contours: circular shapes with a dark perimeter and darker-than-background interior.

        Args:
            gray_or_crop: Either a grayscale image (if cw/ch provided) or a BGR crop
                          from which grayscale will be extracted.
            cw, ch: Width and height of counter_crop. If provided, gray_or_crop is
                    treated as grayscale. If None, gray_or_crop is treated as BGR crop.

        Returns (slot_count, confidence).
        slot_count is the number of detected empty slots (up to objective_total).
        Returns (0, 0.0) when no slots are detected.
        """
        cfg = self.config

        if cw is None or ch is None:
            counter_x = cfg.counter_crop.x1 - cfg.crop.x1
            counter_y = cfg.counter_crop.y1 - cfg.crop.y1
            counter_w = cfg.counter_crop.x2 - cfg.counter_crop.x1
            counter_h = cfg.counter_crop.y2 - cfg.counter_crop.y1

            counter_x = max(0, counter_x)
            counter_y = max(0, counter_y)
            counter_x2 = min(counter_x + counter_w, gray_or_crop.shape[1])
            counter_y2 = min(counter_y + counter_h, gray_or_crop.shape[0])
            cw_local = counter_x2 - counter_x
            ch_local = counter_y2 - counter_y

            if cw_local <= 0 or ch_local <= 0:
                return 0, 0.0

            counter_crop = gray_or_crop[counter_y:counter_y2, counter_x:counter_x2]
            if counter_crop.size == 0:
                return 0, 0.0
            gray = cv2.cvtColor(counter_crop, cv2.COLOR_BGR2GRAY) if len(gray_or_crop.shape) == 3 else counter_crop
        else:
            # gray_or_crop is already grayscale
            gray = gray_or_crop

        if gray.size == 0 or gray.ndim != 2:
            return 0, 0.0

        # Find edges — slots have ring-like contours
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 90)

        # Find contours
        contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if contours is None or len(contours) == 0:
            return 0, 0.0

        # Filter contours that look like circular rings
        slots = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 30 or area > 2000:
                continue

            perimeter = cv2.arcLength(cnt, True)
            if perimeter < 1:
                continue

            circularity = 4 * 3.14159 * area / (perimeter * perimeter)
            if circularity < 0.30:  # Not circular enough
                continue

            # Check if this contour is a ring: the interior should be dark
            # by looking at mean brightness inside vs outside
            x, y, w, h = cv2.boundingRect(cnt)
            # Skip contours that are too wide/tall (likely text or UI elements)
            aspect = w / max(1, h)
            if not (0.5 <= aspect <= 2.0):
                continue

            # Verify the interior of this contour is dark (unfilled)
            cx, cy = x + w // 2, y + h // 2
            try:
                center_val = int(gray[min(cy, gray.shape[0] - 1), min(cx, gray.shape[1] - 1)])
            except (IndexError, ValueError):
                continue

            # Dark interior means unfilled slot
            if center_val < 80:
                slots.append({"area": area, "w": w, "h": h, "circularity": circularity})

        if not slots:
            return 0, 0.0

        slot_count = min(len(slots), cfg.objective_total)

        # Confidence based on slot geometry
        avg_circ = sum(s["circularity"] for s in slots) / len(slots)
        count_score = min(1.0, slot_count / cfg.objective_total)
        shape_score = avg_circ
        conf = round(shape_score * 0.6 + count_score * 0.4, 3)

        return slot_count, conf

    def _count_circles(self, crop: np.ndarray) -> tuple[int | None, float, int, int, float]:
        """
        Count filled circles and empty slots in counter region.

        Returns (count, confidence, filled_candidate_count, slot_count, slot_conf).
        count is filled circle count (capped at objective_total).
        slot_count is empty slot count for 0/4 detection.
        slot_conf is the confidence of the slot detection (based on circularity).
        Returns (None, 0.0, 0, 0, 0.0) when nothing is detected.
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
            return None, 0.0, 0, 0, 0.0

        counter_crop = crop[counter_y:counter_y2, counter_x:counter_x2]
        if counter_crop.size == 0:
            return None, 0.0, 0, 0, 0.0

        gray = cv2.cvtColor(counter_crop, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)

        # ALWAYS detect empty slots first — needed for 0/4 detection at wave start.
        # This must happen before the filled-candidates early-return.
        slot_count, slot_conf = self._count_empty_slots(gray, cw, ch)

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
            # No filled circles. If visible empty slots exist, report 0/4.
            if slot_count > 0:
                return 0, slot_conf, 0, slot_count, slot_conf
            return None, 0.0, 0, 0, 0.0

        count = min(len(candidates), cfg.objective_total)
        candidate_count = len(candidates)

        avg_area = sum(c["area"] for c in candidates) / len(candidates)
        area_score = min(1.0, avg_area / 150.0)
        count_score = min(1.0, count / cfg.objective_total)
        shape_score = min(
            1.0,
            sum(1.0 - abs(1.0 - c["aspect"]) for c in candidates) / max(1, len(candidates)),
        )
        conf = round(area_score * 0.4 + count_score * 0.3 + shape_score * 0.3, 3)

        return count, conf, candidate_count, slot_count, slot_conf

    # ------------------------------------------------------------------
    # Text counter (windowed/non-fullscreen mode)
    # ------------------------------------------------------------------

    def _count_text(self, crop: np.ndarray) -> tuple[int | None, float]:
        """
        Count bright text glyphs in counter region to infer current objective.

        Live GPO renders the text counter as bright stylized glyphs, e.g. "0 / 4".
        We only accept a structured three-glyph sequence: numerator, slash,
        denominator. This prevents random textured background from becoming a
        high-confidence fake 0/4 read.
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
        best_result: tuple[int, float] | None = None

        for text_thresh in [120, 140, 160, 180, 200]:
            _, binary = cv2.threshold(gray, text_thresh, 255, cv2.THRESH_BINARY)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                binary, connectivity=8
            )

            glyphs: list[dict] = []
            for i in range(1, num_labels):
                area = int(stats[i, cv2.CC_STAT_AREA])
                if area < 8 or area > 2500:
                    continue

                x = int(stats[i, cv2.CC_STAT_LEFT])
                y = int(stats[i, cv2.CC_STAT_TOP])
                sw = int(stats[i, cv2.CC_STAT_WIDTH])
                sh = int(stats[i, cv2.CC_STAT_HEIGHT])
                if sw < 2 or sh < 5:
                    continue

                aspect = sw / max(1, sh)
                if not (0.2 <= aspect <= 3.0):
                    continue

                roi = (labels[y : y + sh, x : x + sw] == i).astype(np.uint8) * 255
                glyphs.append({
                    "x": x,
                    "y": y,
                    "cx": float(centroids[i][0]),
                    "cy": float(centroids[i][1]),
                    "w": sw,
                    "h": sh,
                    "area": area,
                    "aspect": aspect,
                    "fill": area / max(1, sw * sh),
                    "holes": self._count_glyph_holes(roi),
                    "roi": roi,
                })

            if len(glyphs) < 3:
                continue

            glyphs.sort(key=lambda g: g["x"])
            for i in range(0, len(glyphs) - 2):
                first, slash, denom = glyphs[i], glyphs[i + 1], glyphs[i + 2]

                if not self._same_text_row(first, slash, denom, ch):
                    continue
                if not self._looks_like_counter_slash(slash, first, denom):
                    continue
                if not self._looks_like_denominator_four(denom):
                    continue

                result_count, digit_conf = self._classify_numerator(first, denom)
                result_count = max(0, min(result_count, cfg.objective_total))

                span = (denom["x"] + denom["w"]) - first["x"]
                span_score = min(1.0, span / max(1, cw * 0.45))
                slash_score = min(1.0, slash["h"] / max(1, max(first["h"], denom["h"])))
                structure_conf = min(1.0, 0.55 + 0.20 * span_score + 0.15 * slash_score)
                conf = round(min(1.0, structure_conf * 0.55 + digit_conf * 0.45), 3)

                if best_result is None or conf > best_result[1]:
                    best_result = (result_count, conf)

        if best_result is None:
            return None, 0.0

        return best_result

    def _count_glyph_holes(self, roi: np.ndarray) -> int:
        contours, hierarchy = cv2.findContours(
            roi, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )
        if hierarchy is None:
            return 0
        holes = 0
        for i in range(len(contours)):
            if hierarchy[0][i][3] != -1:
                holes += 1
        return holes

    def _same_text_row(self, first: dict, slash: dict, denom: dict, height: int) -> bool:
        centers = [first["cy"], slash["cy"], denom["cy"]]
        return max(centers) - min(centers) <= max(12.0, height * 0.30)

    def _looks_like_counter_slash(self, slash: dict, first: dict, denom: dict) -> bool:
        if slash["x"] <= first["x"] or slash["x"] >= denom["x"]:
            return False
        if slash["h"] < min(first["h"], denom["h"]) * 0.55:
            return False
        return slash["aspect"] <= 0.9

    def _looks_like_denominator_four(self, glyph: dict) -> bool:
        if glyph["holes"] > 0:
            return False
        if not (0.35 <= glyph["aspect"] <= 1.1):
            return False
        return 0.20 <= glyph["fill"] <= 0.85

    def _classify_numerator(self, glyph: dict, denominator_four: dict) -> tuple[int, float]:
        if glyph["holes"] >= 1:
            return 0, 0.95

        similarity = self._glyph_similarity(glyph["roi"], denominator_four["roi"])
        if similarity >= 0.70:
            return self.config.objective_total, max(0.86, similarity)

        if glyph["w"] <= denominator_four["w"] * 0.65 or glyph["aspect"] < 0.45:
            return 1, 0.80

        # For 2/4 or 3/4, exact distinction is less important to the HSM than
        # "not clear yet"; keep the read high-confidence but safely incomplete.
        return 2, 0.78

    def _glyph_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        size = (24, 32)
        aa = cv2.resize(a, size, interpolation=cv2.INTER_AREA) > 0
        bb = cv2.resize(b, size, interpolation=cv2.INTER_AREA) > 0
        union = np.logical_or(aa, bb).sum()
        if union == 0:
            return 0.0
        inter = np.logical_and(aa, bb).sum()
        return float(inter / union)
