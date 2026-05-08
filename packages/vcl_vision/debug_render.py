"""Debug renderer: draws annotations on frames for visualization."""
from __future__ import annotations

import cv2
import numpy as np
from typing import Literal

from vcl_core.schemas import ProgressState, CompassState, GameState, Wave1Action, TargetBox


class DebugRenderer:
    """Draws bounding boxes, text overlays, state info on frames."""

    def __init__(self, show_fps: bool = True) -> None:
        self.show_fps = show_fps
        self._frame_times: list[float] = []

    def render(
        self,
        frame: np.ndarray,
        game_state: GameState | None = None,
        progress: ProgressState | None = None,
        compass: CompassState | None = None,
        current_state: str | None = None,
        current_action: Wave1Action | str | None = None,
        haki_targets: list[TargetBox] | None = None,
    ) -> np.ndarray:
        """Draw all debug annotations on the frame and return it."""
        annotated = frame.copy()
        h, w = frame.shape[:2]

        if self.show_fps:
            annotated = self._draw_fps(annotated)

        if progress is not None:
            annotated = self._draw_progress(annotated, progress)

        if compass is not None:
            annotated = self._draw_compass(annotated, compass)

        if current_state:
            annotated = self._draw_state(annotated, current_state)

        if current_action:
            annotated = self._draw_action(annotated, current_action)

        if haki_targets:
            annotated = self._draw_haki_targets(annotated, haki_targets)

        if game_state is not None:
            annotated = self._draw_game_state(annotated, game_state)

        return annotated

    def _draw_fps(self, frame: np.ndarray) -> np.ndarray:
        import time
        now = time.monotonic()
        self._frame_times.append(now)
        self._frame_times = [t for t in self._frame_times if now - t < 1.0]
        fps = len(self._frame_times)
        cv2.putText(
            frame, f"FPS: {fps}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2,
        )
        return frame

    def _draw_progress(self, frame: np.ndarray, progress: ProgressState) -> np.ndarray:
        color = (0, 255, 0) if progress.is_clear else (0, 200, 255)
        text = f"STAGE: {progress.stage_name or 'UNKNOWN'}"
        sub = f"OBJ: {progress.objective_current or '?'}/{progress.objective_total or '?'}"
        conf = f"CONF: {progress.confidence:.2f}"

        cv2.rectangle(frame, (5, 35), (450, 130), (40, 40, 40), -1)
        cv2.putText(frame, text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(frame, sub, (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, conf, (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
        return frame

    def _draw_compass(self, frame: np.ndarray, compass: CompassState) -> np.ndarray:
        h, w = frame.shape[:2]
        text = f"COMPASS: {compass.label or '?'} ({compass.angle_deg or 0:.0f}deg) CONF:{compass.confidence:.2f}"
        cv2.rectangle(frame, (w - 400, 5), (w - 5, 45), (40, 40, 40), -1)
        cv2.putText(
            frame, text, (w - 395, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2,
        )
        return frame

    def _draw_state(self, frame: np.ndarray, state: str) -> np.ndarray:
        h, w = frame.shape[:2]
        text = f"STATE: {state}"
        cv2.rectangle(frame, (5, h - 60), (280, h - 10), (40, 40, 40), -1)
        cv2.putText(frame, text, (10, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        return frame

    def _draw_action(self, frame: np.ndarray, action: Wave1Action | str) -> np.ndarray:
        h, w = frame.shape[:2]
        action_name = action.name if isinstance(action, Wave1Action) else str(action)
        text = f"ACTION: {action_name}"
        cv2.rectangle(frame, (290, h - 60), (600, h - 10), (40, 40, 40), -1)
        cv2.putText(frame, text, (295, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 0), 2)
        return frame

    def _draw_haki_targets(self, frame: np.ndarray, targets: list[TargetBox]) -> np.ndarray:
        for box in targets:
            cv2.rectangle(frame, (box.x1, box.y1), (box.x2, box.y2), (255, 0, 255), 2)
            cv2.putText(
                frame, f"HAKI:{box.confidence:.2f}",
                (box.x1, max(box.y1 - 5, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1,
            )
        return frame

    def _draw_game_state(self, frame: np.ndarray, gs: GameState) -> np.ndarray:
        h, w = frame.shape[:2]
        lines = [
            f"RK_CD: {gs.radiant_kick_cd_remaining:.1f}s",
            f"AIRBORNE: {gs.player_airborne}",
            f"CLEAR_CONF: {gs.clear_confidence:.2f}",
        ]
        start_y = h - 60 - (len(lines) - 1) * 25
        cv2.rectangle(frame, (5, start_y - 5), (310, h - 65), (40, 40, 40), -1)
        for i, line in enumerate(lines):
            cv2.putText(
                frame, line, (10, start_y + i * 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1,
            )
        return frame
