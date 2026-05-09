"""vcl_input — Input executor, primitives, and emergency stop."""
from __future__ import annotations

import sys as _sys
from os.path import dirname as _dn

_PKGS = _dn(_dn(__file__))
if _PKGS not in _sys.path:
    _sys.path.insert(0, _PKGS)
del _sys, _dn, _PKGS

from .primitives import InputPrimitives
from .executor import InputExecutor
from .emergency_stop import EmergencyStop
from .backends import (
    InputBackend,
    PynputInputBackend,
    PyDirectInputBackend,
    PyAutoGUIInputBackend,
    LoggingInputBackend,
    create_input_backend,
)
from .window_focus import (
    get_active_window_title,
    find_windows,
    activate_window,
    ensure_window_focused,
)

__all__ = [
    "InputPrimitives",
    "InputExecutor",
    "EmergencyStop",
    "InputBackend",
    "PynputInputBackend",
    "PyDirectInputBackend",
    "PyAutoGUIInputBackend",
    "LoggingInputBackend",
    "create_input_backend",
    "get_active_window_title",
    "find_windows",
    "activate_window",
    "ensure_window_focused",
]
