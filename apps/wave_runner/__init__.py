"""Wave Runner CLI — dry-run HSM, assist mode, and execute mode for Wave 1."""
from __future__ import annotations

import sys as _sys
from os.path import dirname as _dn

_ROOT = _dn(_dn(_dn(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
del _sys, _dn, _ROOT

from .main import app

__all__ = ["app"]
