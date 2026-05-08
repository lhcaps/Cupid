"""Wave 1 state enumeration."""
from enum import StrEnum


class WaveState(StrEnum):
    """
    States for the dungeon wave-clearing state machine.

    Video analysis (79.5s run):
    - Wave 1 active: t=4.4s - ~18s
    - Heavy combat: t=18-32s
    - Wave 2 active: t=32-44s
    - Heavy combat: t=44-56s
    - Wave 3 active: t=56-68s
    - Heavy combat: t=68-76s
    - Wave 4 active: t=68-76s
    - Victory: t=76s+

    Strategy per wave:
    1. Detect wave UI (conf > 0.3)
    2. Geppo stack
    3. Charged Radiant Kick
    4. Read counter: if 4/x -> wait; if 4/4 -> exit
    5. Repeat for waves 2-4
    6. After Wave 4, move to exit
    """

    BOOT = "BOOT"
    WAIT_PLAYER_CONTROL = "WAIT_PLAYER_CONTROL"
    SETUP_PIKA_V2 = "SETUP_PIKA_V2"
    ENTER_STAGE = "ENTER_STAGE"
    VERIFY_STAGE_UI = "VERIFY_STAGE_UI"

    # Wave clearing loop
    AGGRO_WITH_GEPPO = "AGGRO_WITH_GEPPO"
    CAST_CHARGED_RADIANT_KICK = "CAST_CHARGED_RADIANT_KICK"
    VERIFY_COUNTER = "VERIFY_COUNTER"
    OBS_HAKI_SCAN = "OBS_HAKI_SCAN"
    CLEANUP_IF_NEEDED = "CLEANUP_IF_NEEDED"
    VERIFY_COUNTER_AGAIN = "VERIFY_COUNTER_AGAIN"
    ALIGN_TO_EXIT = "ALIGN_TO_EXIT"

    # Post-clear
    CHECK_NEXT_WAVE = "CHECK_NEXT_WAVE"
    MOVE_NEXT_STAGE = "MOVE_NEXT_STAGE"
    CONFIRM_STAGE_TRANSITION = "CONFIRM_STAGE_TRANSITION"
    DONE = "DONE"
    FAILSAFE = "FAILSAFE"

    @property
    def is_terminal(self) -> bool:
        return self in (self.DONE, self.FAILSAFE)

    @property
    def is_exit_guarded(self) -> bool:
        return self in (
            self.ALIGN_TO_EXIT,
            self.MOVE_NEXT_STAGE,
        )


Wave1State = WaveState
"""Alias: Wave1State is the primary state machine for dungeon wave clearing."""
