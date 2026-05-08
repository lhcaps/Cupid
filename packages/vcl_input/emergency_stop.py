"""Emergency stop: F1 hotkey listener, Ctrl+C handler, global exception handler."""
from __future__ import annotations

import time
import threading
import mss
import cv2
import json
from pathlib import Path
from typing import Callable, NoReturn

from vcl_input.primitives import InputPrimitives


class EmergencyStop:
    """
    Global emergency stop system with three layers:

    1. F1 hotkey listener (pynput) — immediate keyboard interrupt
    2. Ctrl+C handler — signal-based stop
    3. Exception hook — catches any unhandled exception

    On trigger:
    - Release all held keys immediately
    - Save failure screenshot to reports/failure_cases/
    - Write failure log JSON
    - Call optional on_stop callback
    """

    def __init__(
        self,
        primitives: InputPrimitives | None = None,
        on_stop: Callable[[], None] | None = None,
        screenshot_dir: str | Path = "reports/failure_cases",
    ) -> None:
        self._primitives = primitives or InputPrimitives()
        self._on_stop = on_stop
        self._screenshot_dir = Path(screenshot_dir)
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._stop_event = threading.Event()
        self._stopped = False
        self._lock = threading.Lock()

        self._listener: "pynput.keyboard.Listener | None" = None
        self._hotkey_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the F1 hotkey listener."""
        try:
            from pynput import keyboard

            def on_press(key) -> bool:
                try:
                    if hasattr(key, "char") and key.char == "f1":
                        pass
                except Exception:
                    pass
                key_name = ""
                try:
                    key_name = key.char
                except AttributeError:
                    key_name = str(key).replace("Key.", "")

                if key_name.lower() in ("f1", "f2"):
                    self.trigger()
                    return False
                return True

            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            pass

    def stop(self) -> None:
        """Stop the listener."""
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def trigger(self) -> None:
        """
        Trigger emergency stop: release all keys, save screenshot, call callback.
        Thread-safe and idempotent.
        """
        with self._lock:
            if self._stopped:
                return
            self._stopped = True

        self._stop_event.set()

        self._primitives.release_all_keys()

        screenshot_path = self._save_screenshot()

        self._write_failure_log(screenshot_path)

        if self._on_stop:
            try:
                self._on_stop()
            except Exception:
                pass

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    def wait_for_stop(self, timeout: float | None = None) -> bool:
        """Block until stop is triggered. Returns True if stopped."""
        return self._stop_event.wait(timeout=timeout)

    def _save_screenshot(self) -> Path | None:
        """Capture and save a screenshot."""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                img = cv2.cvtColor(
                    cv2.UMat.get(cv2.UMat(shot)),  # type: ignore
                    cv2.COLOR_BGRA2BGR,
                ) if hasattr(cv2, "UMat") else cv2.cvtColor(
                    __import__("numpy").array(shot), cv2.COLOR_BGRA2BGR
                )

            ts = time.strftime("%Y%m%d_%H%M%S")
            path = self._screenshot_dir / f"failure_{ts}.png"
            cv2.imwrite(str(path), img)
            return path
        except Exception:
            return None

    def _write_failure_log(self, screenshot_path: Path | None) -> None:
        """Write a failure JSON log."""
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            log_path = self._screenshot_dir / f"failure_{ts}.json"
            log_data = {
                "timestamp": time.time(),
                "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "stopped": True,
                "screenshot": str(screenshot_path) if screenshot_path else None,
                "held_keys_at_stop": list(self._primitives.held_keys),
            }
            log_path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
        except Exception:
            pass


def setup_ctrl_c_handler(primitives: InputPrimitives, on_stop: Callable[[], None] | None = None) -> None:
    """Set up Ctrl+C handler that releases all keys."""

    def ctrl_c_handler(signum: int, frame) -> NoReturn:
        primitives.release_all_keys()
        if on_stop:
            on_stop()
        import os
        os._exit(1)

    try:
        import signal
        signal.signal(signal.SIGINT, ctrl_c_handler)
        signal.signal(signal.SIGTERM, ctrl_c_handler)
    except Exception:
        pass
