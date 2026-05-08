"""Observation Haki Detector: detects highlighted NPC outlines after G activation."""
from __future__ import annotations

import cv2
import numpy as np

from vcl_core.schemas import TargetBox
from vcl_core.config import ObservationHakiConfig


class HakiState:
    """Result of an Observation Haki scan."""

    def __init__(
        self,
        active: bool = False,
        targets: list[TargetBox] | None = None,
        confidence: float = 0.0,
    ) -> None:
        self.active = active
        self.targets = targets or []
        self.confidence = confidence

    @property
    def has_targets(self) -> bool:
        return self.active and len(self.targets) > 0


class HakiDetector:
    """
    Detects NPC outlines highlighted by Observation Haki (G activation).

    Called after tapping G — captures frames and detects:
    - Bright/glowing outlines around NPCs
    - Haki "vision" color tint (typically blue-white glow)
    - Merges nearby boxes to reduce noise

    NOT a general object detector. Only activates during haki scan window.
    """

    def __init__(self, config: ObservationHakiConfig | None = None) -> None:
        self.config = config or ObservationHakiConfig()
        self._last_scan_frames: list[np.ndarray] = []

    def scan(
        self, frames: list[np.ndarray], min_confidence: float = 0.65
    ) -> HakiState:
        """
        Process a batch of frames captured during haki scan.
        Returns HakiState indicating whether any targets were detected.
        """
        if not frames:
            return HakiState(active=False, confidence=0.0)

        self._last_scan_frames = frames
        all_boxes: list[TargetBox] = []

        for frame in frames:
            boxes = self._detect_haki_outlines(frame)
            all_boxes.extend(boxes)

        merged = self._merge_boxes(all_boxes)
        filtered = [b for b in merged if b.confidence >= min_confidence]

        active = len(filtered) > 0
        avg_conf = (
            sum(b.confidence for b in filtered) / len(filtered)
            if filtered
            else 0.0
        )

        return HakiState(
            active=active,
            targets=filtered,
            confidence=round(avg_conf, 3) if active else 0.0,
        )

    def _detect_haki_outlines(self, frame: np.ndarray) -> list[TargetBox]:
        """
        Detect haki highlight outlines in a single frame.

        Observation Haki typically produces:
        - Blue-white glow (high B channel, lower R)
        - High saturation around target edges
        - Bright outline compared to surroundings
        """
        h, w = frame.shape[:2]
        boxes: list[TargetBox] = []

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        lower_haki = np.array([90, 30, 180])
        upper_haki = np.array([130, 120, 255])
        mask = cv2.inRange(hsv, lower_haki, upper_haki)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 50:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw < 10 or ch < 10 or cw > w * 0.8 or ch > h * 0.8:
                continue

            aspect = cw / max(1, ch)
            if not (0.2 < aspect < 5.0):
                continue

            conf = self._box_confidence(frame[y:y+ch, x:x+cw], mask[y:y+ch, x:x+cw])
            boxes.append(TargetBox(
                x1=x, y1=y, x2=x+cw, y2=y+ch,
                label="haki_target",
                confidence=conf,
            ))

        return boxes

    def _box_confidence(self, region: np.ndarray, mask: np.ndarray) -> float:
        """Compute confidence that a bounding box is a valid haki target."""
        if region.size == 0 or mask.size == 0:
            return 0.0

        fill_ratio = np.sum(mask > 0) / mask.size
        if fill_ratio < 0.05:
            return 0.0

        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if len(region.shape) == 3 else region
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        conf = min(1.0, fill_ratio * 5 + edge_density * 5)
        return round(conf, 3)

    def _merge_boxes(self, boxes: list[TargetBox], iou_threshold: float = 0.3) -> list[TargetBox]:
        """Merge overlapping boxes using non-max suppression."""
        if not boxes:
            return []

        boxes_sorted = sorted(boxes, key=lambda b: b.confidence, reverse=True)
        merged: list[TargetBox] = []
        used = set()

        for i, box_a in enumerate(boxes_sorted):
            if i in used:
                continue
            group = [box_a]
            for j, box_b in enumerate(boxes_sorted[i + 1:], start=i + 1):
                if j in used:
                    continue
                iou = self._iou(box_a, box_b)
                if iou > iou_threshold:
                    group.append(box_b)
                    used.add(j)

            xs = [b.x1 for b in group] + [b.x2 for b in group]
            ys = [b.y1 for b in group] + [b.y2 for b in group]
            avg_conf = sum(b.confidence for b in group) / len(group)

            merged.append(TargetBox(
                x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys),
                label="haki_target",
                confidence=round(avg_conf, 3),
            ))

        return merged

    def _iou(self, a: TargetBox, b: TargetBox) -> float:
        """Compute Intersection over Union between two boxes."""
        xi1 = max(a.x1, b.x1)
        yi1 = max(a.y1, b.y1)
        xi2 = min(a.x2, b.x2)
        yi2 = min(a.y2, b.y2)

        inter_w = max(0, xi2 - xi1)
        inter_h = max(0, yi2 - yi1)
        inter_area = inter_w * inter_h

        area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
        area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
        union_area = area_a + area_b - inter_area

        return inter_area / max(1, union_area)
