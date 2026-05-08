"""YAML configuration loader for VisionCombatLab."""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ScreenConfig(BaseModel):
    width: int = 2560
    height: int = 1440
    fps_target: int = 20


class KeybindsConfig(BaseModel):
    slot_pika_v2: str = "2"
    armament_haki: str = "j"
    observation_haki: str = "g"
    jump: str = "space"
    forward: str = "w"
    backward: str = "s"
    radiant_kick: str = "r"
    dash: str = "q"
    blitz_strike: str = "e"


class CropRegion(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    def to_slice(self) -> tuple[slice, slice]:
        return slice(self.y1, self.y2), slice(self.x1, self.x2)


class ProgressUIConfig(BaseModel):
    crop: CropRegion = Field(default_factory=lambda: CropRegion(x1=1300, y1=0, x2=1850, y2=180))
    counter_crop: CropRegion = Field(default_factory=lambda: CropRegion(x1=1380, y1=110, x2=1620, y2=150))
    wave_panel_crop: CropRegion = Field(default_factory=lambda: CropRegion(x1=1500, y1=0, x2=1760, y2=100))
    stage_name: str = "Shattered Ramparts"
    dungeon_name: str = "Cupid's Ruin"
    objective_total: int = 4
    min_confidence: float = 0.75


class CompassConfig(BaseModel):
    crop: CropRegion = Field(default_factory=lambda: CropRegion(x1=1200, y1=10, x2=1400, y2=60))
    target_exit_heading: str = "S"
    heading_tolerance_deg: int = 15
    rotate_timeout_sec: float = 3.0


class Wave1Config(BaseModel):
    setup_delay_ms: int = 500
    geppo_count: int = 5
    geppo_interval_ms_min: int = 100
    geppo_interval_ms_max: int = 180
    aggro_wait_ms: int = 1000
    radiant_kick_charge_ms: int = 1900
    damage_register_wait_ms: int = 1600
    max_cleanup_cycles: int = 2


class ObservationHakiConfig(BaseModel):
    scan_duration_ms: int = 900
    min_target_confidence: float = 0.65
    max_scans_per_stage: int = 2


class SafetyConfig(BaseModel):
    emergency_stop_key: str = "f1"
    max_state_duration_sec: float = 15.0
    release_all_keys_on_stop: bool = True
    save_failure_screenshot: bool = True


class AppConfig(BaseModel):
    screen: ScreenConfig = Field(default_factory=ScreenConfig)
    keybinds: KeybindsConfig = Field(default_factory=KeybindsConfig)
    progress_ui: ProgressUIConfig = Field(default_factory=ProgressUIConfig)
    compass: CompassConfig = Field(default_factory=CompassConfig)
    wave1: Wave1Config = Field(default_factory=Wave1Config)
    observation_haki: ObservationHakiConfig = Field(default_factory=ObservationHakiConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)


def load_config(path: str | Path) -> AppConfig:
    """Load and validate YAML config file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    raw: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    def _to_crop(data: list[int] | dict) -> CropRegion:
        if isinstance(data, list) and len(data) == 4:
            return CropRegion(x1=data[0], y1=data[1], x2=data[2], y2=data[3])
        if isinstance(data, dict):
            return CropRegion(**data)
        raise ValueError(f"Invalid crop format: {data}")

    cfg = raw.copy()
    for section, key in [
        ("progress_ui", "crop"),
        ("progress_ui", "counter_crop"),
        ("progress_ui", "wave_panel_crop"),
        ("compass", "crop"),
    ]:
        if section in cfg and key in cfg[section]:
            cfg[section][key] = _to_crop(cfg[section][key])

    return AppConfig(**cfg)


def load_default_config() -> AppConfig:
    """Return default app configuration."""
    return AppConfig()
