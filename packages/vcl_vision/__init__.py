"""vcl_vision — Vision components: frame source, detectors, debug renderer."""
from __future__ import annotations

import sys as _sys
from os.path import dirname as _dn, join as _jn

_PKGS = _dn(_dn(__file__))
if _PKGS not in _sys.path:
    _sys.path.insert(0, _PKGS)
del _sys, _dn, _jn, _PKGS

from .frame_source import VideoReader, LiveFrameSource
from .progress_detector import ProgressDetector, ProgressState, ProgressDebugInfo
from .compass_detector import CompassDetector, CompassState
from .haki_detector import HakiDetector, HakiState
from .debug_render import DebugRenderer
from .vision_debug import VisionDebug
from .detections import DetectionBox, WorldDetections
from .yolo_detector import YoloDetector

__all__ = [
    "VideoReader",
    "LiveFrameSource",
    "ProgressDetector",
    "ProgressState",
    "ProgressDebugInfo",
    "CompassDetector",
    "CompassState",
    "HakiDetector",
    "HakiState",
    "DebugRenderer",
    "VisionDebug",
    "DetectionBox",
    "WorldDetections",
    "YoloDetector",
]
