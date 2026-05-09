"""Normalized detection boxes and world detections from YOLO."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DetectionBox(BaseModel):
    """A normalized bounding box from the YOLO detector."""

    label: str
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    def to_pixel_box(self, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        """Convert normalized coords to pixel coordinates."""
        return (
            int(self.x1 * frame_w),
            int(self.y1 * frame_h),
            int(self.x2 * frame_w),
            int(self.y2 * frame_h),
        )


class WorldDetections(BaseModel):
    """Collection of detections returned by the YOLO detector."""

    frame_ts: float = 0.0
    detections: list[DetectionBox] = Field(default_factory=list)

    def filter_by_label(self, label: str) -> list[DetectionBox]:
        return [d for d in self.detections if d.label == label]

    @property
    def enemies(self) -> list[DetectionBox]:
        return self.filter_by_label("enemy")

    @property
    def exits(self) -> list[DetectionBox]:
        return self.filter_by_label("exit")

    @property
    def players(self) -> list[DetectionBox]:
        return self.filter_by_label("player")

    @property
    def progress_panels(self) -> list[DetectionBox]:
        return self.filter_by_label("progress_panel")

    @property
    def objective_counters(self) -> list[DetectionBox]:
        return self.filter_by_label("objective_counter")

    def is_empty(self) -> bool:
        return len(self.detections) == 0
