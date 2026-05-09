"""YOLO detector provider — optional, disabled by default."""
from __future__ import annotations

import logging
from typing import Literal

from vcl_core.config import YoloConfig
from vcl_vision.detections import WorldDetections, DetectionBox

logger = logging.getLogger(__name__)


class YoloDetector:
    """
    Optional YOLO detector provider using Ultralytics.

    Disabled by default. Enable via config.yolo.enabled = true.
    This class never imports ultralytics unless yolo.enabled is True.

    When enabled, detects: enemy, exit, player, progress_panel, objective_counter.
    Does NOT feed into HSM — only logs under debug mode.
    """

    def __init__(self, config: YoloConfig | None = None) -> None:
        self.config = config or YoloConfig()
        self._model: Literal[object] | None = None

        if not self.config.enabled:
            logger.debug("[YOLO] Disabled (config.yolo.enabled=False). No model loaded.")
            return

        self._load_model()

    def _load_model(self) -> None:
        """Lazily load the YOLO model."""
        from pathlib import Path

        model_path = Path(self.config.model_path)
        if not model_path.exists():
            raise RuntimeError(
                f"YOLO model not found at {model_path!r}. "
                f"Train a model with `ultralytics train` or download a checkpoint. "
                f"Until then, set yolo.enabled=false."
            )

        try:
            ultralytics = __import__("ultralytics")
            self._model = ultralytics.YOLO(str(model_path))
            logger.info(
                "[YOLO] Model loaded from %s (classes: %s)",
                model_path,
                self.config.classes.model_dump(),
            )
        except ImportError:
            raise RuntimeError(
                "yolo.enabled=true but ultralytics is not installed. "
                "Install with: pip install ultralytics"
            )

    def detect(self, frame, confidence: float | None = None) -> WorldDetections:
        """
        Run YOLO inference on a frame.

        Args:
            frame: BGR numpy array (HxWx3).
            confidence: Override confidence threshold for this call.

        Returns:
            WorldDetections with normalized bounding boxes.
        """
        if not self.config.enabled or self._model is None:
            return WorldDetections()

        conf_thresh = confidence if confidence is not None else self.config.confidence
        h, w = frame.shape[:2]

        try:
            results = self._model(frame, conf=conf_thresh, device=self.config.device, verbose=False)
        except Exception as exc:
            logger.warning("[YOLO] Inference failed: %s", exc)
            return WorldDetections()

        detections: list[DetectionBox] = []
        cls_map = self.config.classes.model_dump()

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                label = self._id_to_label(cls_id, cls_map)
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].item())

                detections.append(DetectionBox(
                    label=label,
                    x1=float(x1) / w,
                    y1=float(y1) / h,
                    x2=float(x2) / w,
                    y2=float(y2) / h,
                    confidence=conf,
                ))

        return WorldDetections(detections=detections)

    def _id_to_label(self, cls_id: int, cls_map: dict) -> str:
        """Map a class ID to a label name."""
        inverse = {v: k for k, v in cls_map.items()}
        return inverse.get(cls_id, f"class_{cls_id}")

    def log_detections(self, detections: WorldDetections, ts: float) -> None:
        """Log detection summary under debug mode."""
        if not detections.is_empty():
            logger.debug(
                "[YOLO] t=%.3f detections=%d enemies=%d exits=%d panels=%d",
                ts,
                len(detections.detections),
                len(detections.enemies),
                len(detections.exits),
                len(detections.progress_panels),
            )
