"""Time base utilities for VisionCombatLab."""
from __future__ import annotations

import time
from typing import Callable

from functools import wraps


class Clock:
    """Monotonic clock wrapper with pause/resume support."""

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._paused_at: float | None = None
        self._accumulated_pause: float = 0.0

    def now(self) -> float:
        """Seconds since clock creation (pauses excluded)."""
        if self._paused_at is not None:
            return self._paused_at - self._start - self._accumulated_pause
        return time.monotonic() - self._start - self._accumulated_pause

    def pause(self) -> None:
        if self._paused_at is None:
            self._paused_at = time.monotonic()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._accumulated_pause += time.monotonic() - self._paused_at
            self._paused_at = None

    def reset(self) -> None:
        self._start = time.monotonic()
        self._paused_at = None
        self._accumulated_pause = 0.0

    def elapsed_ms(self) -> float:
        return self.now() * 1000.0


class CooldownTracker:
    """Tracks cooldowns for combat abilities."""

    def __init__(self) -> None:
        self._cooldowns: dict[str, float] = {}

    def start(self, name: str, duration_sec: float) -> None:
        self._cooldowns[name] = duration_sec

    def remaining(self, name: str) -> float:
        """Seconds remaining on cooldown. Returns 0 if not on cooldown."""
        dur = self._cooldowns.get(name, 0.0)
        return max(0.0, dur)

    def tick(self, dt_sec: float) -> None:
        for k in list(self._cooldowns):
            self._cooldowns[k] = max(0.0, self._cooldowns[k] - dt_sec)
            if self._cooldowns[k] <= 0.0:
                del self._cooldowns[k]


def sleep_with_stopcheck(duration_sec: float, stop_flag: Callable[[], bool]) -> bool:
    """
    Sleep in small increments while checking stop flag.
    Returns True if sleep completed normally, False if stopped early.
    """
    interval = 0.05
    elapsed = 0.0
    while elapsed < duration_sec:
        if stop_flag():
            return False
        time.sleep(min(interval, duration_sec - elapsed))
        elapsed += interval
    return True


def rate_limited(min_interval_sec: float) -> Callable:
    """Decorator: enforce minimum interval between calls."""
    last_call = [0.0]

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            now = time.monotonic()
            wait = min_interval_sec - (now - last_call[0])
            if wait > 0:
                time.sleep(wait)
            last_call[0] = time.monotonic()
            return fn(*args, **kwargs)

        return wrapper

    return decorator
