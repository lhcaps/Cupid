"""Counter stability tracker: requires N consecutive high-confidence 4/4 reads before exiting."""
from __future__ import annotations


class CounterStabilityTracker:
    """
    Requires N consecutive high-confidence readings of 4/4 before reporting stable.

    Prevents false exit from a single noisy 4/4 frame followed by unclear reading.
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

    @property
    def last_reads(self) -> list[tuple[int | None, float]]:
        return list(self._reads)

    def reset(self) -> None:
        """Clear all recorded reads."""
        self._reads.clear()
