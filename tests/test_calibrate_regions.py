"""Tests for the region calibration tool (P0.7 Part B).

Covers: roi_xywh_to_box conversion, YAML structure update,
and preservation of unrelated config fields.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

import sys
_ROOT = Path(__file__).resolve().parent.parent
for p in [str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "apps")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from vcl_core.config import load_config, AppConfig, CropRegion
from tools.calibrate_regions import (
    roi_xywh_to_box,
    box_to_crop_region,
    update_config_with_rois,
)


class TestRoiConversion:
    def test_roi_xywh_to_box_basic(self):
        """x,y,w,h from cv2.selectROI converts to x1,y1,x2,y2."""
        box = roi_xywh_to_box(100, 200, 300, 400)
        assert box == [100, 200, 400, 600]

    def test_roi_xywh_to_box_zero_dimensions(self):
        """Zero-width / zero-height ROI must produce x2==x1 or y2==y1."""
        box = roi_xywh_to_box(50, 50, 0, 0)
        assert box == [50, 50, 50, 50]
        assert box[2] == box[0]
        assert box[3] == box[1]

    def test_roi_xywh_to_box_order(self):
        """x2 = x + w, y2 = y + h (no swap on negative coords)."""
        box = roi_xywh_to_box(-10, 50, 100, 200)
        assert box == [-10, 50, 90, 250]
        assert box[2] == box[0] + 100
        assert box[3] == box[1] + 200

    def test_box_to_crop_region_round_trip(self):
        """CropRegion -> box -> CropRegion round-trip preserves values."""
        original = CropRegion(x1=100, y1=200, x2=400, y2=600)
        box = [original.x1, original.y1, original.x2, original.y2]
        rebuilt = box_to_crop_region(box)
        assert rebuilt.x1 == original.x1
        assert rebuilt.y1 == original.y1
        assert rebuilt.x2 == original.x2
        assert rebuilt.y2 == original.y2


class TestConfigUpdate:
    def test_calibration_updates_yaml_structure(self):
        """update_config_with_rois must write correct x1,y1,x2,y2 values."""
        cfg = load_config(_ROOT / "configs" / "wave1.shattered_ramparts.yaml")

        new_progress = [1300, 0, 1850, 180]
        new_counter = [1380, 110, 1620, 150]
        new_wave_panel = [1500, 0, 1760, 100]
        new_compass = [1200, 10, 1400, 60]

        updated = update_config_with_rois(
            cfg, new_progress, new_counter, new_wave_panel, new_compass
        )

        assert updated["progress_ui"]["crop"] == new_progress
        assert updated["progress_ui"]["counter_crop"] == new_counter
        assert updated["progress_ui"]["wave_panel_crop"] == new_wave_panel
        assert updated["compass"]["crop"] == new_compass

    def test_calibration_preserves_unrelated_config_fields(self):
        """Fields outside the 4 selected crops must be preserved unchanged."""
        cfg = load_config(_ROOT / "configs" / "wave1.shattered_ramparts.yaml")

        untouched_fields = {
            "screen": cfg.model_dump()["screen"],
            "keybinds": cfg.model_dump()["keybinds"],
            "wave1": cfg.model_dump()["wave1"],
            "observation_haki": cfg.model_dump()["observation_haki"],
            "safety": cfg.model_dump()["safety"],
        }

        dummy_boxes = [100, 0, 500, 200]

        updated = update_config_with_rois(
            cfg,
            progress_crop=dummy_boxes,
            counter_crop=dummy_boxes,
            wave_panel_crop=dummy_boxes,
            compass_crop=dummy_boxes,
        )

        for section, original_value in untouched_fields.items():
            assert updated[section] == original_value, (
                f"Section '{section}' was mutated; it must be preserved"
            )

    def test_updated_yaml_round_trip(self):
        """Config dict written to YAML and reloaded must have correct values."""
        cfg = load_config(_ROOT / "configs" / "wave1.shattered_ramparts.yaml")

        new_progress = [1300, 0, 1850, 180]
        new_counter = [1380, 110, 1620, 150]
        new_wave_panel = [1500, 0, 1760, 100]
        new_compass = [1200, 10, 1400, 60]

        updated = update_config_with_rois(
            cfg, new_progress, new_counter, new_wave_panel, new_compass
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as fh:
            yaml.dump(updated, fh, default_flow_style=None, sort_keys=False)
            tmp_path = fh.name

        try:
            reloaded = load_config(tmp_path)

            assert reloaded.progress_ui.crop.x1 == new_progress[0]
            assert reloaded.progress_ui.crop.y1 == new_progress[1]
            assert reloaded.progress_ui.crop.x2 == new_progress[2]
            assert reloaded.progress_ui.crop.y2 == new_progress[3]

            assert reloaded.progress_ui.counter_crop.x1 == new_counter[0]
            assert reloaded.compass.crop.x1 == new_compass[0]

            assert reloaded.wave1.radiant_kick_charge_ms == cfg.wave1.radiant_kick_charge_ms
            assert reloaded.screen.width == cfg.screen.width
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_update_config_with_rois_returns_dict(self):
        """Must return a plain dict suitable for yaml.dump()."""
        cfg = load_config(_ROOT / "configs" / "wave1.shattered_ramparts.yaml")
        result = update_config_with_rois(
            cfg,
            progress_crop=[0, 0, 100, 100],
            counter_crop=[0, 0, 100, 100],
            wave_panel_crop=[0, 0, 100, 100],
            compass_crop=[0, 0, 100, 100],
        )
        assert isinstance(result, dict)
        assert "progress_ui" in result
        assert "compass" in result
