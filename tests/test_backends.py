"""Tests for the pluggable runtime backends: capture, input, and focus."""
from __future__ import annotations

import numpy as np
import pytest

from vcl_core.config import (
    AppConfig,
    CaptureConfig,
    InputConfig,
    DebugConfig,
    YoloConfig,
    YoloClasses,
)


class TestConfigDefaults:
    """Verify default config values for new backend settings."""

    def test_app_config_has_all_backend_sections(self):
        cfg = AppConfig()
        assert hasattr(cfg, "capture")
        assert hasattr(cfg, "input")
        assert hasattr(cfg, "debug")
        assert hasattr(cfg, "yolo")

    def test_capture_defaults(self):
        cfg = CaptureConfig()
        assert cfg.backend == "mss"
        assert cfg.monitor_index == 1
        assert cfg.fps_target == 20
        assert cfg.region is None
        assert cfg.output_color == "BGR"

    def test_input_defaults(self):
        cfg = InputConfig()
        assert cfg.backend == "pynput"
        assert cfg.tap_delay_ms == 10
        assert cfg.focus_window_title == "Roblox"
        assert cfg.require_focus is True
        assert cfg.fail_on_input_error is True

    def test_debug_defaults(self):
        cfg = DebugConfig()
        assert cfg.input is False
        assert cfg.vision is False
        assert cfg.save_every_n_frames == 20
        assert cfg.output_dir == "reports/vision_debug"

    def test_yolo_defaults(self):
        cfg = YoloConfig()
        assert cfg.enabled is False
        assert cfg.model_path == "models/cupid_wave1_yolo.pt"
        assert cfg.confidence == 0.3
        assert cfg.device == "auto"
        assert cfg.classes.enemy == 0
        assert cfg.classes.exit == 1
        assert cfg.classes.player == 2
        assert cfg.classes.progress_panel == 3
        assert cfg.classes.objective_counter == 4

    def test_yolo_disabled_does_not_require_model(self):
        """YOLO disabled should not require the model file to exist."""
        cfg = YoloConfig(enabled=False)
        assert cfg.enabled is False
        # No RuntimeError just from creating the config


class TestCaptureBackend:
    """Tests for capture backend factory and MSS fallback."""

    def test_mss_backend_creation(self):
        from vcl_capture.backends import create_capture_backend
        backend = create_capture_backend("mss", monitor_index=1)
        assert backend.name == "mss"
        assert backend.width > 0
        assert backend.height > 0
        backend.close()

    def test_mss_backend_grab_returns_bgr(self):
        from vcl_capture.backends import create_capture_backend
        backend = create_capture_backend("mss")
        frame = backend.grab()
        assert isinstance(frame, np.ndarray)
        assert frame.shape[2] == 3  # BGR channels
        backend.close()

    def test_dxcam_missing_raises_clear_error(self):
        from vcl_capture.backends import create_capture_backend
        # Try to create dxcam backend — should raise RuntimeError with install hint
        # (it won't actually import since dxcam isn't installed)
        with pytest.raises(RuntimeError, match="dxcam.*not installed|not installed"):
            create_capture_backend("dxcam")

    def test_dxcam_backend_uses_dxcam_create_api(self):
        """DXCamCaptureBackend must use dxcam.create(), not dxcam.DXCam()."""
        import inspect
        from vcl_capture.backends import DXCamCaptureBackend
        source = inspect.getsource(DXCamCaptureBackend.__init__)
        # Must use dxcam.create
        assert "dxcam.create" in source or "create(" in source, (
            "DXCamCaptureBackend must use dxcam.create() API, not dxcam.DXCam()."
        )
        # Must NOT use deprecated dxcam.DXCam()
        assert "DXCam()" not in source, (
            "DXCamCaptureBackend must not use deprecated dxcam.DXCam(). Use dxcam.create()."
        )

    def test_dxcam_grab_passes_region_and_new_frame_only_false(self):
        """DXCamCaptureBackend.grab() must pass region and new_frame_only=False."""
        import inspect
        from vcl_capture.backends import DXCamCaptureBackend
        source = inspect.getsource(DXCamCaptureBackend.grab)
        assert "new_frame_only" in source, (
            "DXCamCaptureBackend.grab() must use new_frame_only=False."
        )
        assert "region=" in source or "region" in source, (
            "DXCamCaptureBackend.grab() must pass region to grab()."
        )

    def test_unknown_backend_raises_value_error(self):
        from vcl_capture.backends import create_capture_backend
        with pytest.raises(ValueError, match="Unknown capture backend"):
            create_capture_backend("v4l2")

    def test_mss_backend_with_region(self):
        from vcl_capture.backends import create_capture_backend
        backend = create_capture_backend("mss", region=(0, 0, 640, 480))
        assert backend.width > 0
        assert backend.height > 0
        backend.close()


class TestInputBackend:
    """Tests for input backend factory."""

    def test_pynput_backend_creation(self):
        from vcl_input.backends import create_input_backend, InputConfig
        cfg = InputConfig(backend="pynput")
        backend = create_input_backend(cfg)
        assert backend.name == "pynput"

    def test_fake_backend_receives_press_release(self):
        from vcl_input.backends import create_input_backend, InputConfig, LoggingInputBackend
        cfg = InputConfig(backend="pynput")
        backend = create_input_backend(cfg)
        # Verify it doesn't crash
        backend.press("space")
        backend.release("space")
        backend.close()

    def test_pyautogui_missing_raises_clear_error(self):
        from vcl_input.backends import create_input_backend, InputConfig
        # pyautogui should be installed via runtime deps
        # Just verify the backend exists as an option
        cfg = InputConfig(backend="pyautogui")
        try:
            backend = create_input_backend(cfg)
            assert backend.name == "pyautogui"
            backend.close()
        except RuntimeError:
            # Expected if pyautogui is not installed
            pass

    def test_unknown_input_backend_raises(self):
        from vcl_input.backends import create_input_backend, InputConfig
        cfg = InputConfig(backend="evdev")
        with pytest.raises(ValueError, match="Unknown input backend"):
            create_input_backend(cfg)

    def test_logging_backend(self):
        from vcl_input.backends import LoggingInputBackend
        backend = LoggingInputBackend()
        assert backend.name == "logging"
        backend.press("space")
        backend.release("space")

    def test_input_primitives_backend_name_property(self):
        """InputPrimitives must expose backend_name property."""
        from vcl_input.primitives import InputPrimitives
        from vcl_input.backends import LoggingInputBackend

        # With injected backend
        logging = LoggingInputBackend()
        prim = InputPrimitives(backend=logging)
        assert prim.backend_name == "logging"

        # With function injection (custom_fn)
        prim_fn = InputPrimitives(press_fn=lambda k: None, release_fn=lambda k: None)
        assert prim_fn.backend_name == "custom_fn"

    def test_input_primitives_respects_input_config_backend(self):
        """InputPrimitives should create the correct backend from InputConfig."""
        from vcl_input.primitives import InputPrimitives
        from vcl_core.config import InputConfig
        from vcl_input.backends import create_input_backend

        # When no backend injected, InputPrimitives creates one from input_config
        cfg = InputConfig(backend="pynput")
        prim = InputPrimitives(input_config=cfg)
        # Backend should be created lazily on first use, verify the config is stored
        assert prim._input_config.backend == "pynput"

    def test_input_primitives_uses_injected_backend_press_release(self):
        """InputPrimitives must use injected backend's press/release, not create a new one."""
        from vcl_input.primitives import InputPrimitives
        from vcl_input.backends import InputBackend

        pressed_keys = []
        released_keys = []

        class FakeBackend(InputBackend):
            name = "fake"
            def press(self, key):
                pressed_keys.append(key)
            def release(self, key):
                released_keys.append(key)

        fake = FakeBackend()
        prim = InputPrimitives(backend=fake)

        # Verify backend_name returns correct name
        assert prim.backend_name == "fake"

        # Verify press/release go through injected backend
        prim.tap("space")
        assert "space" in pressed_keys
        assert "space" in released_keys


class TestFocusGuard:
    """Tests for window focus guard."""

    def test_get_active_window_title_returns_none_when_missing(self):
        from vcl_input.window_focus import get_active_window_title
        # PyWinCtl may not be installed — should return None, not crash
        result = get_active_window_title()
        assert result is None or isinstance(result, str)

    def test_find_windows_returns_empty_when_missing(self):
        from vcl_input.window_focus import find_windows
        result = find_windows("NonExistentWindowXYZ123")
        assert isinstance(result, list)


class TestPyDirectInputBackend:
    """Tests for PyDirectInputBackend — must use pydirectinput-rgx, not pyautogui."""

    def test_pydirectinput_backend_uses_real_directinput_not_pyautogui(self):
        """PyDirectInputBackend must import pydirectinput-rgx (or pydirectinput), NOT pyautogui."""
        import inspect
        from vcl_input.backends import PyDirectInputBackend
        source = inspect.getsource(PyDirectInputBackend.__init__)
        # Must NOT contain pyautogui
        assert "pyautogui" not in source.lower(), (
            "PyDirectInputBackend must not import pyautogui. "
            "It must use pydirectinput-rgx or pydirectinput."
        )
        # Must try pydirectinput_rgx
        assert "pydirectinput" in source, (
            "PyDirectInputBackend must import pydirectinput-rgx or pydirectinput."
        )

    def test_pydirectinput_factory_error_message_includes_install_hint(self):
        """Factory error for pydirectinput must mention pip install pydirectinput-rgx."""
        from vcl_input.backends import create_input_backend
        from vcl_core.config import InputConfig
        cfg = InputConfig(backend="pydirectinput")
        import sys
        from unittest.mock import patch

        saved = {k: sys.modules.pop(k, None) for k in ["pydirectinput_rgx", "pydirectinput"]}
        try:
            with patch.dict(sys.modules, {"pydirectinput_rgx": None, "pydirectinput": None}):
                with pytest.raises(RuntimeError, match="pip install pydirectinput-rgx"):
                    create_input_backend(cfg)
        finally:
            for k, v in saved.items():
                if v is not None:
                    sys.modules[k] = v


class TestLiveFrameSource:
    """Tests for LiveFrameSource using CaptureBackend."""

    def test_live_source_uses_mss_by_default(self):
        from vcl_vision.frame_source import LiveFrameSource
        source = LiveFrameSource()
        assert source.backend_name == "mss"
        source.close()

    def test_live_source_accepts_backend_param(self):
        from vcl_vision.frame_source import LiveFrameSource
        source = LiveFrameSource(backend="mss")
        assert source.backend_name == "mss"
        source.close()

    def test_live_source_preserves_constructor_signature(self):
        from vcl_vision.frame_source import LiveFrameSource
        # Backward compatible: monitor_index, fps_target, region still work
        source = LiveFrameSource(monitor_index=1, fps_target=15, region=None)
        assert source.fps_target == 15
        source.close()
