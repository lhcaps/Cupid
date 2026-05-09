"""Window focus guard using PyWinCtl for Roblox window management."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_pywinctl():
    """Lazy import PyWinCtl, raises RuntimeError on failure."""
    try:
        import pywinctl as pw
        return pw
    except ImportError:
        raise RuntimeError(
            "PyWinCtl is required for window focus features. "
            "It is not installed. Install with: pip install pywinctl"
        )


def get_active_window_title() -> str | None:
    """Return the title of the currently active (foreground) window."""
    try:
        pw = _get_pywinctl()
        win = pw.getActiveWindow()
        return win.title if win else None
    except RuntimeError:
        return None


def find_windows(title_contains: str) -> list[str]:
    """
    Find all window titles containing the given substring (case-insensitive).

    Returns list of matching window titles.
    """
    try:
        pw = _get_pywinctl()
        all_wins = pw.getAllWindows()
        return [w.title for w in all_wins if title_contains.lower() in w.title.lower()]
    except RuntimeError:
        return []


def activate_window(title_contains: str) -> bool:
    """
    Activate (bring to foreground) a window whose title contains the given substring.

    Returns True if a matching window was found and activated.
    """
    try:
        pw = _get_pywinctl()
        all_wins = pw.getAllWindows()
        for win in all_wins:
            if title_contains.lower() in win.title.lower():
                win.activate()
                return True
        return False
    except RuntimeError:
        return False


def ensure_window_focused(
    title_contains: str,
    require: bool = True,
) -> tuple[bool, str]:
    """
    Ensure a window with the given title substring is active.

    Args:
        title_contains: Substring to search in window titles.
        require: If True, raises RuntimeError when PyWinCtl is missing.

    Returns:
        (focused, message) tuple.
        focused=True means the target window is the active foreground.
    """
    try:
        pw = _get_pywinctl()
    except RuntimeError as e:
        if require:
            raise RuntimeError(
                f"Window focus is required but PyWinCtl is not installed: {e}"
            )
        return False, f"Window focus skipped (PyWinCtl unavailable): {e}"

    active_title = get_active_window_title()
    if active_title and title_contains.lower() in active_title.lower():
        return True, f"Window already focused: {active_title!r}"

    matching = find_windows(title_contains)
    if not matching:
        msg = f"No window found containing {title_contains!r}"
        if require:
            raise RuntimeError(msg)
        return False, msg

    activated = activate_window(title_contains)
    if activated:
        return True, f"Activated window: {matching[0]!r}"

    msg = f"Failed to activate window containing {title_contains!r}. Found: {matching}"
    return False, msg
