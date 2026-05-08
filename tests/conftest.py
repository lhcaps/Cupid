"""pytest configuration: add packages/ to sys.path for all tests."""
from __future__ import annotations

import sys
from os.path import dirname, join

_ROOT = dirname(dirname(__file__))
_PKGS = join(_ROOT, "packages")
_APPS = join(_ROOT, "apps")

for p in [_ROOT, _PKGS, _APPS]:
    if p not in sys.path:
        sys.path.insert(0, p)
