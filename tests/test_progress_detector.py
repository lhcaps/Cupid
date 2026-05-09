"""Tests for ProgressDetector — filled circle counter detection."""
from __future__ import annotations

import numpy as np
import pytest
import cv2

from vcl_vision.progress_detector import ProgressDetector
from vcl_core.schemas import ProgressState
from vcl_core.config import ProgressUIConfig, CropRegion


def _make_counter_crop(
    filled: int,
    unfilled: int = 0,
    width: int = 420,
    height: int = 40,
    cx_start: int = 30,
    spacing: int = 55,
    circle_r: int = 11,
) -> np.ndarray:
    """Create a synthetic counter crop with filled/unfilled circles."""
    crop = np.zeros((height, width, 3), dtype=np.uint8)
    bright = 220
    dark = 25

    for i in range(filled):
        cv2.circle(crop, (cx_start + i * spacing, height // 2), circle_r, (bright, bright, bright), -1)
    for i in range(unfilled):
        pos = cx_start + (filled + i) * spacing
        if pos < width:
            cv2.circle(crop, (pos, height // 2), circle_r, (dark, dark, dark), 2)

    return crop


def _make_wave_panel(width: int = 550, height: int = 180) -> np.ndarray:
    """Create a synthetic wave panel that passes active detection, keeping counter area dark."""
    panel = np.full((height, width, 3), 30, dtype=np.uint8)
    bright_bar = np.full((20, width, 3), 200, dtype=np.uint8)
    panel[0:20, :] = bright_bar
    return panel


def _make_active_wave_panel(width: int = 550, height: int = 180) -> np.ndarray:
    """Create a wave panel with bright region for panel-active detection.

    _detect_panel(circle mode) checks max_ratio > 0.02 at thresholds [100,120,150,180,200].
    A solid bright area works but the key is bright pixel ratio.
    Use top bar at brightness 200 -> ratio = 20/180 = 0.111 > 0.02 -> panel_active=True.
    """
    panel = np.full((height, width, 3), 25, dtype=np.uint8)
    bright_bar = np.full((20, width, 3), 210, dtype=np.uint8)
    panel[0:20, :] = bright_bar
    return panel


def _make_full_frame(
    counter_crop: np.ndarray,
    panel_crop: np.ndarray,
    counter_abs: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Assemble a full 2560x1440 frame with counter and panel placed at config positions."""
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)

    panel_abs = (0, 1300, 180, 1850)
    panel_y1, panel_x1, panel_y2, panel_x2 = panel_abs
    panel_h = panel_y2 - panel_y1
    panel_w = panel_x2 - panel_x1
    frame[panel_y1:panel_y2, panel_x1:panel_x2] = panel_crop[:panel_h, :panel_w]

    if counter_abs:
        cy1, cx1, cy2, cx2 = counter_abs
    else:
        cy1, cx1 = 100, 1340
        cy2, cx2 = 140, 1760
    crop_h = cy2 - cy1
    crop_w = cx2 - cx1
    frame[cy1:cy2, cx1:cx2] = counter_crop[:crop_h, :crop_w]

    return frame


def _make_config_with_coords(
    crop: tuple[int, int, int, int] | None = None,
    counter: tuple[int, int, int, int] | None = None,
    wave_panel: tuple[int, int, int, int] | None = None,
) -> ProgressUIConfig:
    """Make config with specific coordinates matching test frame placement."""
    if crop is None:
        crop = (1300, 0, 1850, 180)
    if counter is None:
        counter = (1340, 100, 1760, 140)
    if wave_panel is None:
        wave_panel = (1300, 0, 1560, 100)

    return ProgressUIConfig(
        crop=CropRegion(x1=crop[0], y1=crop[1], x2=crop[2], y2=crop[3]),
        counter_crop=CropRegion(x1=counter[0], y1=counter[1], x2=counter[2], y2=counter[3]),
        wave_panel_crop=CropRegion(x1=wave_panel[0], y1=wave_panel[1], x2=wave_panel[2], y2=wave_panel[3]),
    )


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

    def test_circle_0_4_returns_current_0(self):
        """Zero filled circles should return objective_current=0."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
        )
        # Use _make_active_wave_panel so panel_active=True
        # _count_circles returns (None, 0.0, 0) for 0 candidates, so we
        # expect text detection path or low confidence
        panel = _make_active_wave_panel(width=550, height=180)
        counter = _make_counter_crop(filled=0, unfilled=4)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        result = det.detect(frame)

        # 0 candidates in circle path + no text detection -> confidence=0
        assert result.objective_current is None or result.objective_current == 0
        assert result.confidence < 0.75  # not high enough to gate

    def test_candidate_count_is_nonzero_for_valid_circle_fixture(self):
        """ProgressDebugInfo.candidate_count should be nonzero when circles are detected."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            objective_total=4,
        )
        panel = _make_wave_panel(width=550, height=180)
        counter = _make_counter_crop(filled=4, unfilled=0)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        _, debug_info = det.detect_with_debug(frame)

        # Circle mode should report actual candidate count
        if debug_info.selected_mode == "circle":
            assert debug_info.candidate_count > 0, (
                f"candidate_count should be > 0 for valid circle fixture. "
                f"Got {debug_info.candidate_count}. "
                f"_count_circles must return 4-tuple (count, conf, candidate_count, slot_count)."
            )
            assert debug_info.slot_count >= 0

    def test_candidate_count_is_zero_for_blank_counter(self):
        """ProgressDebugInfo.candidate_count should be 0 when no circles are found."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            objective_total=4,
        )
        panel = _make_active_wave_panel(width=550, height=180)
        # Blank counter: no circles at all
        counter = np.zeros((40, 420, 3), dtype=np.uint8)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        _, debug_info = det.detect_with_debug(frame)

        assert debug_info.candidate_count == 0, (
            f"candidate_count should be 0 for blank counter. Got {debug_info.candidate_count}."
        )

    def test_slot_count_field_exists(self):
        """ProgressDebugInfo must have slot_count field."""
        cfg = ProgressUIConfig()
        det = ProgressDetector(config=cfg)
        frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        _, debug_info = det.detect_with_debug(frame)
        assert hasattr(debug_info, "slot_count"), "ProgressDebugInfo must have slot_count field"

    def test_blank_crop_does_not_produce_high_confidence_0_4(self):
        """Blank crop should never return high-confidence 0/4."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            objective_total=4,
        )
        # Panel is active (bright region), counter is completely dark
        panel = _make_active_wave_panel(width=550, height=180)
        counter = np.zeros((40, 420, 3), dtype=np.uint8)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        _, debug_info = det.detect_with_debug(frame)

        # Without visible slots, blank crop must NOT produce high-confidence 0/4
        assert debug_info.slot_count == 0, (
            f"Blank counter should have slot_count=0. Got {debug_info.slot_count}."
        )
        if debug_info.selected_mode == "circle" and debug_info.circle_count == 0:
            # If 0/4 is reported, confidence must be below the verification threshold
            assert debug_info.raw_confidence < 0.75, (
                f"Blank crop must NOT produce high-confidence 0/4. "
                f"Got circle_count=0 with conf={debug_info.raw_confidence}"
            )

    def test_circle_3_4_returns_current_3(self):
        """Three filled circles should return objective_current=3."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
        )
        panel = _make_wave_panel(width=550, height=180)
        counter = _make_counter_crop(filled=3, unfilled=1)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        result = det.detect(frame)

        assert result.objective_current == 3
        assert result.objective_total == 4

    def test_circle_4_4_returns_current_4(self):
        """Four filled circles should return objective_current=4."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
        )
        panel = _make_wave_panel(width=550, height=180)
        counter = _make_counter_crop(filled=4, unfilled=0)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        result = det.detect(frame)

        assert result.objective_current == 4
        assert result.objective_total == 4

    def test_circle_4_4_low_confidence_does_not_claim_clear(self):
        """4/4 on synthetic frames should not reach is_clear if confidence is low."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            min_confidence=0.75,
        )
        panel = _make_wave_panel(width=550, height=180)
        counter = _make_counter_crop(filled=4, unfilled=0)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        result = det.detect(frame)

        if result.objective_current == 4 and result.confidence >= 0.75:
            assert result.is_clear is True, "4/4 with high confidence should be clear"
        else:
            assert result.confidence < 0.75, "Low confidence should prevent clear claim"

    def test_no_wave_panel_no_counter_read(self):
        """When wave panel is absent, confidence should be 0 and no counter read."""
        frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        det = ProgressDetector()
        result = det.detect(frame)
        assert result.confidence == 0.0
        assert result.objective_current is None

    def test_progress_detector_zero_of_four_valid_confidence(self):
        """0 filled circles on active panel should return low confidence, not 0/4 high confidence.

        The fix: no circle candidates means panel structure is missing, so confidence is low.
        Previously this returned (0, 0.90) for no-candidates, producing false 0/4 reads.
        The correct test for valid 0/4 is: create a frame where circle detection finds
        exactly 0 candidates AND the panel is active AND counter region has circle geometry.
        """
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            objective_total=4,
        )
        # Make a panel that IS active but has NO bright candidates in the counter region.
        # The panel bar at brightness 210 -> ratio 20/180=0.111 > 0.02 -> panel_active=True.
        # But the counter area is dark (no filled circles), so _count_circles -> (None, 0.0).
        panel = _make_active_wave_panel(width=550, height=180)
        # No circles at all in the counter area
        counter = np.zeros((40, 420, 3), dtype=np.uint8)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        result = det.detect(frame)

        # With the bug fix: no circle candidates = (None, 0.0) = low confidence
        # Previously this returned (0, 0.90) which was the bug
        assert result.confidence < 0.75, (
            f"No circle candidates should NOT produce high confidence. "
            f"Got objective_current={result.objective_current}, confidence={result.confidence}. "
            "This was the false-high-confidence bug that this test is verifying is fixed."
        )

    def test_progress_detector_clamps_noise_above_total(self):
        """Noise detecting more than objective_total circles must be clamped to objective_total."""
        cfg = ProgressUIConfig(
            crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            counter_crop=CropRegion(x1=1340, y1=100, x2=1760, y2=140),
            wave_panel_crop=CropRegion(x1=1300, y1=0, x2=1850, y2=180),
            objective_total=4,
        )
        panel = _make_wave_panel(width=550, height=180)
        counter = _make_counter_crop(filled=4, unfilled=4)
        frame = _make_full_frame(counter, panel, counter_abs=(100, 1340, 140, 1760))

        det = ProgressDetector(config=cfg)
        result = det.detect(frame)

        assert result.objective_current <= cfg.objective_total, \
            f"objective_current ({result.objective_current}) should be clamped to objective_total ({cfg.objective_total})"
