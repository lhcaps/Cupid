#!/usr/bin/env python3
"""Region calibration tool — select progress/counter/compass ROIs on a live or static screenshot.

Usage:
    python tools/calibrate_regions.py --config configs/wave1.shattered_ramparts.yaml --out configs/wave1.local.yaml
    python tools/calibrate_regions.py --image path/to/screenshot.png --config configs/wave1.shattered_ramparts.yaml --out out.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

# Ensure packages are importable
_ROOT = Path(__file__).resolve().parent.parent
for p in [str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "apps")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from vcl_core.config import load_config, AppConfig, CropRegion
from vcl_vision.progress_detector import ProgressDetector
from vcl_vision.compass_detector import CompassDetector


def roi_xywh_to_box(x: int, y: int, w: int, h: int) -> list[int]:
    """Convert cv2.selectROI output (x, y, w, h) to [x1, y1, x2, y2]."""
    return [x, y, x + w, y + h]


def box_to_crop_region(box: list[int]) -> CropRegion:
    """Convert [x1, y1, x2, y2] to a CropRegion."""
    return CropRegion(x1=box[0], y1=box[1], x2=box[2], y2=box[3])


def update_config_with_rois(
    config: AppConfig,
    progress_crop: list[int],
    counter_crop: list[int],
    wave_panel_crop: list[int],
    compass_crop: list[int],
) -> dict:
    """Merge selected ROI boxes into a config dict and return a YAML-compatible dict."""
    updated = config.model_dump()

    def box_to_yaml_region(box: list[int]) -> list[int]:
        return [box[0], box[1], box[2], box[3]]

    updated["progress_ui"]["crop"] = box_to_yaml_region(progress_crop)
    updated["progress_ui"]["counter_crop"] = box_to_yaml_region(counter_crop)
    updated["progress_ui"]["wave_panel_crop"] = box_to_yaml_region(wave_panel_crop)
    updated["compass"]["crop"] = box_to_yaml_region(compass_crop)

    return updated


def draw_debug_overlay(
    frame: np.ndarray,
    progress_crop: list[int],
    counter_crop: list[int],
    wave_panel_crop: list[int],
    compass_crop: list[int],
    progress_state,
    compass_state,
) -> np.ndarray:
    """Draw ROI boxes on the frame and annotate detection results."""
    overlay = frame.copy()

    color_map = [
        (progress_crop, (0, 255, 0), "progress_ui.crop"),
        (counter_crop, (255, 0, 0), "progress_ui.counter_crop"),
        (wave_panel_crop, (0, 200, 255), "progress_ui.wave_panel_crop"),
        (compass_crop, (200, 0, 200), "compass.crop"),
    ]

    for box, color, label in color_map:
        x1, y1, x2, y2 = box
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            overlay, label, (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1,
        )

    # Annotate detection results
    if progress_state is not None:
        prog_text = (
            f"progress: {progress_state.objective_current}/{progress_state.objective_total} "
            f"conf={progress_state.confidence:.2f}"
        )
        cv2.putText(overlay, prog_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    if compass_state is not None:
        compass_text = (
            f"compass: {compass_state.label or '?'} "
            f"conf={compass_state.confidence:.2f}"
        )
        cv2.putText(overlay, compass_text, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 0, 200), 2)

    return overlay


def capture_live_screenshot(monitor_index: int = 1) -> np.ndarray:
    """Capture a screenshot from the given monitor index using mss."""
    import mss
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        screenshot = sct.grab(monitor)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate progress UI and compass crop regions on a screenshot."
    )
    parser.add_argument(
        "--config", "-c", type=Path, required=True,
        help="Source YAML config file",
    )
    parser.add_argument(
        "--out", "-o", type=Path, required=True,
        help="Output YAML config file (must differ from --config to avoid accidental mutation)",
    )
    parser.add_argument(
        "--image", type=Path,
        help="Use a static image instead of live capture",
    )
    parser.add_argument(
        "--monitor", type=int, default=1,
        help="Monitor index for mss (default: 1)",
    )
    args = parser.parse_args()

    # Guard: don't accidentally mutate the source config
    if args.out.resolve() == args.config.resolve():
        print(
            "[ERROR] --out cannot be the same as --config. "
            "Please use a different output path.",
            file=sys.stderr,
        )
        return 1

    if not args.config.exists():
        print(f"[ERROR] Config file not found: {args.config}", file=sys.stderr)
        return 1

    # Load source config
    base_config = load_config(args.config)
    print(f"[INFO] Loaded config from: {args.config}")

    # Capture or load frame
    if args.image:
        if not args.image.exists():
            print(f"[ERROR] Image not found: {args.image}", file=sys.stderr)
            return 1
        frame = cv2.imread(str(args.image))
        if frame is None:
            print(f"[ERROR] Could not read image: {args.image}", file=sys.stderr)
            return 1
        print(f"[INFO] Loaded image: {args.image}  shape={frame.shape}")
    else:
        print("[INFO] Capturing live screenshot...")
        try:
            frame = capture_live_screenshot(args.monitor)
        except Exception as exc:
            print(f"[ERROR] Live capture failed: {exc}", file=sys.stderr)
            return 1
        print(f"[INFO] Captured screenshot  shape={frame.shape}")

    # Show rescaled preview for easier ROI selection
    preview_scale = 0.7
    preview_w = int(frame.shape[1] * preview_scale)
    preview_h = int(frame.shape[0] * preview_scale)
    preview = cv2.resize(frame, (preview_w, preview_h))
    cv2.putText(
        preview,
        "Click & drag to select region. Press ENTER or SPACE to confirm. Press 'r' to reset. ESC to cancel.",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
    )
    cv2.namedWindow("VCL Region Calibration", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("VCL Region Calibration", preview_w, preview_h)
    cv2.imshow("VCL Region Calibration", preview)

    regions = [
        ("progress_ui.crop", base_config.progress_ui.crop),
        ("progress_ui.counter_crop", base_config.progress_ui.counter_crop),
        ("progress_ui.wave_panel_crop", base_config.progress_ui.wave_panel_crop),
        ("compass.crop", base_config.compass.crop),
    ]

    selected_boxes: dict[str, list[int]] = {}

    for name, default_crop in regions:
        print(f"\n[ROI] Selecting: {name}")
        print(f"       Default: [x1={default_crop.x1}, y1={default_crop.y1}, "
              f"x2={default_crop.x2}, y2={default_crop.y2}]")

        # Scale default ROI to preview coordinates
        dx1 = int(default_crop.x1 * preview_scale)
        dy1 = int(default_crop.y1 * preview_scale)
        dx2 = int(default_crop.x2 * preview_scale)
        dy2 = int(default_crop.y2 * preview_scale)

        cv2.putText(
            preview,
            f"Selecting: {name}  (press any key...)",
            (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2,
        )
        cv2.imshow("VCL Region Calibration", preview)

        roi = cv2.selectROI(
            "VCL Region Calibration",
            preview,
            fromCenter=False,
            showCrosshair=True,
        )
        cv2.destroyWindow("VCL Region Calibration")

        x, y, w, h = roi
        if w == 0 and h == 0:
            print(f"       [SKIP] No selection — keeping default")
            # Keep default, scale back to full resolution
            selected_boxes[name] = [default_crop.x1, default_crop.y1, default_crop.x2, default_crop.y2]
        else:
            # Convert from preview-scale ROI back to full-resolution box
            fx1 = int(x / preview_scale)
            fy1 = int(y / preview_scale)
            fx2 = int((x + w) / preview_scale)
            fy2 = int((y + h) / preview_scale)
            selected_boxes[name] = [fx1, fy1, fx2, fy2]
            print(f"       Selected: [x1={fx1}, y1={fy1}, x2={fx2}, y2={fy2}]  (w={w}, h={h} preview)")

        # Rebuild preview
        preview = cv2.resize(frame.copy(), (preview_w, preview_h))
        cv2.putText(
            preview,
            "Next: press any key to continue, 'r' to reset, ESC to cancel",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
        )
        cv2.namedWindow("VCL Region Calibration", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("VCL Region Calibration", preview_w, preview_h)
        cv2.imshow("VCL Region Calibration", preview)
        key = cv2.waitKey(0)
        cv2.destroyWindow("VCL Region Calibration")
        if key == 27:  # ESC
            print("\n[ABORT] Calibration cancelled by user.")
            return 130

    cv2.destroyAllWindows()

    progress_crop = selected_boxes["progress_ui.crop"]
    counter_crop = selected_boxes["progress_ui.counter_crop"]
    wave_panel_crop = selected_boxes["progress_ui.wave_panel_crop"]
    compass_crop = selected_boxes["compass.crop"]

    print("\n" + "=" * 60)
    print("SELECTED BOXES")
    print("=" * 60)
    print(f"  progress_ui.crop       : {progress_crop}")
    print(f"  progress_ui.counter_crop: {counter_crop}")
    print(f"  progress_ui.wave_panel_crop: {wave_panel_crop}")
    print(f"  compass.crop          : {compass_crop}")

    # Build updated config
    updated_config = update_config_with_rois(
        base_config,
        progress_crop,
        counter_crop,
        wave_panel_crop,
        compass_crop,
    )

    # Run detectors on the captured frame
    print("\n" + "=" * 60)
    print("DETECTION RESULTS ON CAPTURED FRAME")
    print("=" * 60)

    from vcl_core.config import ProgressUIConfig, CompassConfig

    det_cfg = base_config.model_copy(deep=True)
    det_cfg.progress_ui = ProgressUIConfig(
        crop=box_to_crop_region(progress_crop),
        counter_crop=box_to_crop_region(counter_crop),
        wave_panel_crop=box_to_crop_region(wave_panel_crop),
        stage_name=base_config.progress_ui.stage_name,
        dungeon_name=base_config.progress_ui.dungeon_name,
        objective_total=base_config.progress_ui.objective_total,
        min_confidence=base_config.progress_ui.min_confidence,
    )
    det_cfg.compass = CompassConfig(
        crop=box_to_crop_region(compass_crop),
        target_exit_heading=base_config.compass.target_exit_heading,
        heading_tolerance_deg=base_config.compass.heading_tolerance_deg,
        rotate_timeout_sec=base_config.compass.rotate_timeout_sec,
    )

    progress_det = ProgressDetector(det_cfg.progress_ui)
    compass_det = CompassDetector(det_cfg.compass)

    try:
        progress_state = progress_det.detect(frame)
        print(f"  Progress: {progress_state.objective_current}/{progress_state.objective_total}  "
              f"confidence={progress_state.confidence:.3f}")
    except Exception as exc:
        print(f"  Progress detection error: {exc}")
        progress_state = None

    try:
        compass_state = compass_det.detect(frame)
        print(f"  Compass: label={compass_state.label or '?'}  "
              f"confidence={compass_state.confidence:.3f}")
    except Exception as exc:
        print(f"  Compass detection error: {exc}")
        compass_state = None

    # Save debug overlay
    overlay = draw_debug_overlay(
        frame,
        progress_crop,
        counter_crop,
        wave_panel_crop,
        compass_crop,
        progress_state,
        compass_state,
    )
    reports_dir = _ROOT / "reports" / "calibration"
    reports_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = reports_dir / "latest_overlay.jpg"
    cv2.imwrite(str(overlay_path), overlay)
    print(f"\n[INFO] Debug overlay saved: {overlay_path}")

    # Write output YAML
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        yaml.dump(updated_config, f, default_flow_style=None, sort_keys=False)
    print(f"[INFO] Config written: {args.out}")

    print("\n[DONE] Calibration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
