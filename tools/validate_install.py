#!/usr/bin/env python3
"""Validate that all VCL packages and dependencies are importable."""
from __future__ import annotations

import sys
from os.path import dirname, join

_ROOT = dirname(dirname(__file__))
_PKGS = join(_ROOT, "packages")
_APPS = join(_ROOT, "apps")

for p in [_ROOT, _PKGS, _APPS]:
    if p not in sys.path:
        sys.path.insert(0, p)


def check(name: str, import_fn) -> bool:
    try:
        import_fn()
        print(f"  [OK] {name}")
        return True
    except ImportError as e:
        print(f"  [MISSING] {name}: {e}")
        return False


def main() -> int:
    print("VisionCombatLab - Installation Validator")
    print("=" * 40)

    deps = [
        ("cv2 (OpenCV)", lambda: __import__("cv2")),
        ("numpy", lambda: __import__("numpy")),
        ("pydantic", lambda: __import__("pydantic")),
        ("yaml", lambda: __import__("yaml")),
        ("rich", lambda: __import__("rich")),
        ("mss", lambda: __import__("mss")),
        ("pytest", lambda: __import__("pytest")),
        ("typer (optional)", lambda: __import__("typer")),
        ("pynput (optional)", lambda: __import__("pynput")),
    ]

    print("Dependency checks:")
    ok = True
    for name, fn in deps:
        if not check(name, fn):
            ok = False

    print()
    print("Package imports:")
    packages = [
        ("vcl_core", lambda: __import__("vcl_core")),
        ("vcl_vision", lambda: __import__("vcl_vision")),
        ("vcl_hsm", lambda: __import__("vcl_hsm")),
        ("vcl_input", lambda: __import__("vcl_input")),
        ("vcl_eval", lambda: __import__("vcl_eval")),
    ]
    for name, fn in packages:
        if not check(name, fn):
            ok = False

    print()
    print("Required deps for pip install:")
    print("  pip install opencv-python numpy pydantic pyyaml rich mss pytest")
    print()
    print("Optional deps for live execution:")
    print("  pip install typer pynput")
    print()

    if ok:
        print("All checks passed!")
        return 0
    else:
        print("Some checks failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
