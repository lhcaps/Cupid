"""vcl_capture — Pluggable screen capture backends."""
from __future__ import annotations

import sys as _sys
from os.path import dirname as _dn

_PKGS = _dn(_dn(__file__))
if _PKGS not in _sys.path:
    _sys.path.insert(0, _PKGS)
del _sys, _dn, _PKGS

from .backends import (
    CaptureBackend,
    MSSCaptureBackend,
    DXCamCaptureBackend,
    create_capture_backend,
)

__all__ = [
    "CaptureBackend",
    "MSSCaptureBackend",
    "DXCamCaptureBackend",
    "create_capture_backend",
]
