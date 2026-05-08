"""Tests for ProgressDetector."""
from __future__ import annotations

import numpy as np
import pytest

from vcl_vision.progress_detector import ProgressDetector
from vcl_core.schemas import ProgressState
from vcl_core.config import ProgressUIConfig


def make_frame_with_ui(
    stage_text: str = "",
    counter_text: str = "0 / 4",
    brightness: int = 240,
    has_ui: bool = True,
) -> np.ndarray:
    """Create a synthetic frame with UI panel at top-left."""
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    if has_ui:
        ui_panel = frame[0:190, 0:560]
        ui_panel[:] = [brightness, brightness, brightness]

        if stage_text:
            pass
        if counter_text:
            pass
    return frame


class TestProgressDetector:
    def test_detector_returns_low_confidence_when_no_ui(self):
        """When UI panel is absent, confidence should be 0.0."""
        frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        det = ProgressDetector()
        result = det.detect(frame)
        assert result.confidence == 0.0

    def test_detector_never_fakes_clear_state(self):
        """Detector must never report 4/4 when confidence is low."""
        frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        det = ProgressDetector(config=ProgressUIConfig(min_confidence=0.75))
        result = det.detect(frame)
        assert result.is_clear is False

    def test_empty_crop_returns_zero_confidence(self):
        """Empty crop should not crash and should return zero confidence."""
        det = ProgressDetector()
        result = det.detect(np.zeros((10, 10, 3), dtype=np.uint8))
        assert result.confidence == 0.0

    def test_progress_state_defaults(self):
        """Default ProgressState should have null fields."""
        state = ProgressState()
        assert state.stage_name is None
        assert state.objective_current is None
        assert state.objective_total is None
        assert state.confidence == 0.0

    def test_is_clear_requires_high_confidence(self):
        """is_clear should only be True when confidence >= 0.75."""
        state = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=4,
            objective_total=4,
            confidence=0.74,
        )
        assert state.is_clear is False

        state_high_conf = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=4,
            objective_total=4,
            confidence=0.76,
        )
        assert state_high_conf.is_clear is True

    def test_is_clear_requires_correct_values(self):
        """is_clear needs both current=4 and total=4."""
        state = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=3,
            objective_total=4,
            confidence=0.9,
        )
        assert state.is_clear is False

        state2 = ProgressState(
            stage_name="Shattered Ramparts",
            objective_current=4,
            objective_total=3,
            confidence=0.9,
        )
        assert state2.is_clear is False
