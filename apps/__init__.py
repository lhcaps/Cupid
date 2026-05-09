"""Apps package."""
from __future__ import annotations

import sys
from os.path import dirname, join

_ROOT = dirname(dirname(__file__))
_PKGS = join(_ROOT, "packages")

for p in [_ROOT, _PKGS]:
    if p not in sys.path:
        sys.path.insert(0, p)
