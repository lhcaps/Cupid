"""Pydantic schemas for VisionCombatLab data models."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TargetBox(BaseModel):
    """Bounding box for a detected target (NPC or Haki outline)."""

    x1: int
    y1: int
    x2: int
    y2: int
    label: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def center_x(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def center_y(self) -> int:
        return (self.y1 + self.y2) // 2


class ProgressState(BaseModel):
    """Parsed state from the progress UI (top-left panel)."""

    stage_name: str | None = None
    dungeon_name: str | None = None
    objective_current: int | None = None
    objective_total: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def is_clear(self) -> bool:
        """True only when counter reads 4/4 with high confidence."""
        return (
            self.objective_current == 4
            and self.objective_total == 4
            and self.confidence >= 0.75
        )


class CompassState(BaseModel):
    """Parsed compass heading from top compass bar."""

    label: str | None = None
    angle_deg: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GameState(BaseModel):
    """Full game state snapshot consumed by the HSM."""

    timestamp: float
    source: Literal["video", "live"]

    stage_name: str | None = None
    stage_confidence: float = 0.0

    objective_current: int | None = None
    objective_total: int | None = None
    objective_confidence: float = 0.0

    compass_heading: str | None = None
    compass_angle_deg: float | None = None
    compass_confidence: float = 0.0

    observation_haki_active: bool = False
    haki_targets: list[TargetBox] = Field(default_factory=list)

    radiant_kick_cd_remaining: float = 0.0
    player_airborne: bool | None = None

    clear_confidence: float = 0.0


class Wave1ActionName(str, Enum):
    """Enumeration of all possible Wave 1 actions."""

    WAIT = "WAIT"
    PRESS_SLOT_2 = "PRESS_SLOT_2"
    PRESS_ARMAMENT_HAKI = "PRESS_ARMAMENT_HAKI"
    ENTER_STAGE = "ENTER_STAGE"
    GEPPO_STACK = "GEPPO_STACK"
    HOLD_RADIANT_KICK = "HOLD_RADIANT_KICK"
    RELEASE_RADIANT_KICK = "RELEASE_RADIANT_KICK"
    READ_PROGRESS = "READ_PROGRESS"
    OBSERVATION_SCAN = "OBSERVATION_SCAN"
    CLEANUP_TARGET = "CLEANUP_TARGET"
    ALIGN_COMPASS = "ALIGN_COMPASS"
    MOVE_TO_EXIT = "MOVE_TO_EXIT"
    STOP_FAILSAFE = "STOP_FAILSAFE"


class Wave1Action(BaseModel):
    """An action produced by the Wave 1 HSM."""

    name: Wave1ActionName
    reason: str
    duration_ms: int | None = None


class RunLogEntry(BaseModel):
    """Single entry in the JSONL run log."""

    run_id: str
    state: str
    timestamp: float
    progress: str | None = None
    compass: str | None = None
    action: str
    confidence: dict[str, float] = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Summary of a complete Wave 1 run."""

    run_id: str
    status: Literal["clear", "fail", "stopped"]
    duration_sec: float
    objective_final: str
    radiant_kick_casts: int = 0
    observation_scans: int = 0
    cleanup_cycles: int = 0
    stuck_retries: int = 0
    failure_reason: str | None = None
