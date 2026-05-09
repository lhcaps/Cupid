"""Counter stability tracker: requires N consecutive high-confidence 4/4 reads before exiting.

Also tracks whether the counter has ever shown a high count in the current window,
to reject impossible resets (e.g., 4/4 -> 0/4) during gameplay.
"""
from __future__ import annotations


class CounterStabilityTracker:
    """
    Requires N consecutive high-confidence readings of N/4 before reporting stable.

    Prevents false exit from a single noisy 4/4 frame followed by unclear reading.
    Also detects impossible counter resets (e.g., 4/4 -> 0/4) that cannot happen
    without a stage transition.
    Designed to be unit-testable and HSM-agnostic.
    """

    def __init__(
        self,
        window_size: int = 3,
        required_count: int = 3,
        required_objective: int = 4,
        min_confidence: float = 0.65,
    ) -> None:
        self.window_size = window_size
        self.required_count = required_count
        self.required_objective = required_objective
        self.min_confidence = min_confidence
        self._reads: list[tuple[int | None, float]] = []

    def update(
        self,
        objective_current: int | None,
        objective_total: int | None,
        confidence: float,
    ) -> None:
        """Record a new progress reading."""
        self._reads.append((objective_current, confidence))
        if len(self._reads) > self.window_size:
            self._reads.pop(0)

    def is_stable_clear(self) -> bool:
        """
        Return True only when:
        - All reads in the window show objective_current == required_objective
        - All reads have confidence >= min_confidence
        - Number of qualifying reads >= required_count
        """
        if len(self._reads) < self.required_count:
            return False

        qualifying = 0
        for obj_cur, conf in self._reads:
            if (
                obj_cur == self.required_objective
                and conf >= self.min_confidence
            ):
                qualifying += 1

        return qualifying >= self.required_count

    def saw_high_count(self) -> bool:
        """
        Return True if any read in the window showed objective_current >= required_objective
        with sufficient confidence. Used to detect impossible counter resets.
        """
        for obj_cur, conf in self._reads:
            if (
                obj_cur is not None
                and obj_cur >= self.required_objective
                and conf >= self.min_confidence
            ):
                return True
        return False

    def is_impossible_drop(self, current: int | None, total: int | None, confidence: float) -> bool:
        """
        Return True if we have seen a high count (>= required_objective) in this window
        but the current read shows a significantly lower count. This is an impossible
        counter reset during normal gameplay and should be rejected.

        Only returns True when:
        - We have previously seen >= required_objective with good confidence
        - Current read is significantly lower (>= 2 below required_objective)
        - Current read has reasonable confidence
        """
        if not self.saw_high_count():
            return False
        if current is None or confidence < self.min_confidence:
            return False
        # Reject drop of 2 or more below required_objective (e.g., 4/4 -> 0/4 or 4/4 -> 1/4)
        if current < self.required_objective - 1:
            return True
        return False

    @property
    def last_reads(self) -> list[tuple[int | None, float]]:
        return list(self._reads)

    def reset(self) -> None:
        """Clear all recorded reads."""
        self._reads.clear()
