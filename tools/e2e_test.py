#!/usr/bin/env python3
"""End-to-end pipeline test: analyze video -> HSM dry-run."""
from __future__ import annotations

import sys
sys.path.insert(0, "e:/Macro/Cupid/packages")
sys.path.insert(0, "e:/Macro/Cupid")

import json
import cv2
from vcl_core.config import load_config
from vcl_vision.frame_source import VideoReader
from vcl_vision.progress_detector import ProgressDetector
from vcl_vision.compass_detector import CompassDetector
from vcl_hsm import Wave1HSM


def main():
    video_path = r"e:/Macro/Cupid/MedalTVRoblox20260509053121278-trim-1778279513526.mp4"
    config_path = r"e:/Macro/Cupid/configs/wave1.shattered_ramparts.yaml"
    config = load_config(config_path)

    progress_det = ProgressDetector(config.progress_ui)
    compass_det = CompassDetector(config.compass)
    hsm = Wave1HSM(config=config)

    print("=== E2E Pipeline Test ===")
    print("Video: " + video_path)

    vr = VideoReader(video_path)
    print("Video: {}x{} @ {:.1f}fps, {:.1f}s".format(vr.width, vr.height, vr.fps, vr.duration_sec))

    timeline = []
    for ts, frame in vr.iter_sampled(2.0):
        progress = progress_det.detect(frame)
        compass = compass_det.detect(frame)
        action = hsm.tick(
            game_state=None,
            progress=progress,
            compass=compass,
            current_time=ts,
        )
        timeline.append({
            "t": round(ts, 2),
            "state": hsm.state.value,
            "action": action.name.value,
            "progress_conf": progress.confidence,
            "progress_obj": "{}/{}".format(progress.objective_current, progress.objective_total),
            "compass": compass.label,
        })

    vr.close()

    print("\nHSM final state: " + hsm.state.value)
    print("Stats: " + str(hsm.stats))

    state_counts = {}
    for entry in timeline:
        state = entry["state"]
        state_counts[state] = state_counts.get(state, 0) + 1

    print("\nState distribution:")
    for state, count in sorted(state_counts.items()):
        print("  {}: {}".format(state, count))

    print("\nSample entries:")
    for entry in timeline[:5]:
        print("  t={:5.1f}s [{:25s}] action={:25s} obj={} conf={:.2f}".format(
            entry["t"], entry["state"], entry["action"], entry["progress_obj"], entry["progress_conf"]))

    print("\n[OK] E2E pipeline PASSED")


if __name__ == "__main__":
    main()
