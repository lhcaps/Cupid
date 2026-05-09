"""Pluggable keyboard/mouse input backends."""
from __future__ import annotations

import abc
import logging

from vcl_core.config import InputConfig

logger = logging.getLogger(__name__)


class InputBackend(abc.ABC):
    """Abstract keyboard input backend interface."""

    name: str = "abstract"

    @abc.abstractmethod
    def press(self, key: str) -> None:
        """Press a key down."""
        ...

    @abc.abstractmethod
    def release(self, key: str) -> None:
        """Release a key."""
        ...

    def close(self) -> None:
        """Release backend resources. Override if needed."""


class PynputInputBackend(InputBackend):
    """
    pynput-based input backend.
    Always available as default fallback.
    """

    name = "pynput"

    def __init__(self) -> None:
        from pynput.keyboard import Controller, Key
        self._controller = Controller()
        self._Key = Key

    def press(self, key: str) -> None:
        k = self._resolve_key(key)
        self._controller.press(k)

    def release(self, key: str) -> None:
        k = self._resolve_key(key)
        self._controller.release(k)

    def _resolve_key(self, key: str) -> str:
        k = getattr(self._Key, key, None)
        if k is None:
            try:
                return self._Key._value_(key)
            except Exception:
                return key
        return k


class PyDirectInputBackend(InputBackend):
    """
    DirectInput-compatible input backend using pydirectinput-rgx.

    Uses SendInput() + scan codes for DirectX/game compatibility.
    Tries pydirectinput-rgx first (better DirectInput coverage), then pydirectinput.

    Requires: pip install pydirectinput-rgx
              or pip install pydirectinput
    """

    name = "pydirectinput"

    def __init__(self) -> None:
        pdi = None
        try:
            import pydirectinput_rgx as pdi
        except ImportError:
            try:
                import pydirectinput as pdi
            except ImportError:
                raise RuntimeError(
                    "pydirectinput backend selected but neither pydirectinput-rgx "
                    "nor pydirectinput is installed. "
                    "Install with: pip install pydirectinput-rgx"
                ) from None
        self._pdi = pdi
        try:
            self._pdi.FAILSAFE = False
        except AttributeError:
            pass

    def press(self, key: str) -> None:
        self._pdi.keyDown(key)

    def release(self, key: str) -> None:
        self._pdi.keyUp(key)

    def close(self) -> None:
        pass


class PyAutoGUIInputBackend(InputBackend):
    """
    PyAutoGUI-based input backend.
    General-purpose fallback for non-game environments.
    """

    name = "pyautogui"

    def __init__(self) -> None:
        pyautogui = __import__("pyautogui")
        self._pyautogui = pyautogui
        self._pyautogui.FAILSAFE = False

    def press(self, key: str) -> None:
        self._pyautogui.keyDown(key)

    def release(self, key: str) -> None:
        self._pyautogui.keyUp(key)

    def close(self) -> None:
        pass


def create_input_backend(config: InputConfig | None = None) -> InputBackend:
    """
    Factory: create an InputBackend by name.

    Args:
        config: InputConfig with backend name and error handling settings.

    Returns:
        An InputBackend instance.
    """
    name = (config.backend if config else "pynput").lower().strip()

    if name == "pynput":
        return PynputInputBackend()

    if name == "pydirectinput":
        return PyDirectInputBackend()

    if name == "pyautogui":
        try:
            return PyAutoGUIInputBackend()
        except ImportError:
            raise RuntimeError(
                "pyautogui backend selected but pyautogui is not installed. "
                "Install with: pip install pyautogui"
            )

    raise ValueError(
        f"Unknown input backend: {config.backend!r}. Use 'pynput', 'pydirectinput', or 'pyautogui'."
    )


class LoggingInputBackend(InputBackend):
    """
    No-op backend that logs press/release calls without sending real input.
    Use for assist/dry-run modes.
    """

    name = "logging"

    def press(self, key: str) -> None:
        logger.debug("[INPUT] press(%r)", key)

    def release(self, key: str) -> None:
        logger.debug("[INPUT] release(%r)", key)
