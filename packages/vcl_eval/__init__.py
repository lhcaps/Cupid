"""vcl_eval — Evaluation metrics and report generation."""
from __future__ import annotations

import sys as _sys
from os.path import dirname as _dn

_PKGS = _dn(_dn(__file__))
if _PKGS not in _sys.path:
    _sys.path.insert(0, _PKGS)
del _sys, _dn, _PKGS

from .metrics import RunMetrics, compute_metrics
from .report import ReportGenerator

__all__ = ["RunMetrics", "compute_metrics", "ReportGenerator"]
