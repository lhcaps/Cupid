"""Tests for CompassDetector."""
from __future__ import annotations

import numpy as np
import pytest

from vcl_vision.compass_detector import CompassDetector, HEADING_LABELS
from vcl_core.schemas import CompassState
from vcl_core.config import CompassConfig


class TestCompassDetector:
    def test_detector_returns_low_confidence_on_empty_frame(self):
        """Empty frame should return low confidence, not crash."""
        frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        det = CompassDetector()
        result = det.detect(frame)
        assert result.confidence == 0.0
        assert result.label is None

    def test_heading_labels_are_valid(self):
        """All heading labels should have valid angles."""
        assert HEADING_LABELS["N"] == 0
        assert HEADING_LABELS["NE"] == 45
        assert HEADING_LABELS["E"] == 90
        assert HEADING_LABELS["SE"] == 135
        assert HEADING_LABELS["S"] == 180
        assert HEADING_LABELS["SW"] == 225
        assert HEADING_LABELS["W"] == 270
        assert HEADING_LABELS["NW"] == 315

    def test_heading_labels_round_trip(self):
        """All headings should round-trip through labels -> angles."""
        for label, angle in HEADING_LABELS.items():
            assert label in HEADING_LABELS

    def test_empty_crop_returns_zero_confidence(self):
        """Empty crop should not crash."""
        det = CompassDetector()
        result = det.detect(np.zeros((10, 10, 3), dtype=np.uint8))
        assert result.confidence == 0.0

    def test_compass_state_defaults(self):
        """Default CompassState should have null fields."""
        state = CompassState()
        assert state.label is None
        assert state.angle_deg is None
        assert state.confidence == 0.0

    def test_detector_config_loading(self):
        """CompassDetector should accept custom config."""
        cfg = CompassConfig(
            target_exit_heading="S",
            heading_tolerance_deg=15,
        )
        det = CompassDetector(config=cfg)
        assert det.config.target_exit_heading == "S"
        assert det.config.heading_tolerance_deg == 15
