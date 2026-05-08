"""Run metrics computation from JSONL logs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from vcl_core.schemas import RunSummary


class RunMetrics:
    """Aggregated metrics for a batch of Wave 1 runs."""

    def __init__(self) -> None:
        self.total_runs = 0
        self.cleared_runs = 0
        self.failed_runs = 0
        self.stopped_runs = 0
        self._durations: list[float] = []
        self._radiant_kicks: list[int] = []
        self._observation_scans: list[int] = []
        self._cleanup_cycles: list[int] = []
        self._false_exits = 0
        self._emergency_stops = 0
        self._runs_by_id: dict[str, RunSummary] = {}

    def add_summary(self, summary: RunSummary) -> None:
        self._runs_by_id[summary.run_id] = summary
        self.total_runs += 1
        if summary.status == "clear":
            self.cleared_runs += 1
        elif summary.status == "fail":
            self.failed_runs += 1
        elif summary.status == "stopped":
            self.stopped_runs += 1
        self._durations.append(summary.duration_sec)
        self._radiant_kicks.append(summary.radiant_kick_casts)
        self._observation_scans.append(summary.observation_scans)
        self._cleanup_cycles.append(summary.cleanup_cycles)

    def add_false_exit(self) -> None:
        self._false_exits += 1

    def add_emergency_stop(self) -> None:
        self._emergency_stops += 1

    @property
    def clear_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.cleared_runs / self.total_runs

    @property
    def mean_clear_time(self) -> float:
        cleared = [d for d, s in zip(self._durations, self._runs_by_id.values()) if s.status == "clear"]
        if not cleared:
            return 0.0
        return sum(cleared) / len(cleared)

    @property
    def false_exit_count(self) -> int:
        return self._false_exits

    @property
    def emergency_stop_count(self) -> int:
        return self._emergency_stops

    def summary_dict(self) -> dict:
        return {
            "total_runs": self.total_runs,
            "cleared_runs": self.cleared_runs,
            "failed_runs": self.failed_runs,
            "stopped_runs": self.stopped_runs,
            "clear_rate": round(self.clear_rate, 3),
            "mean_clear_time_sec": round(self.mean_clear_time, 2),
            "false_exit_count": self._false_exits,
            "emergency_stop_count": self._emergency_stops,
            "mean_radiant_kicks": round(sum(self._radiant_kicks) / max(1, len(self._radiant_kicks)), 2),
            "mean_observation_scans": round(sum(self._observation_scans) / max(1, len(self._observation_scans)), 2),
            "mean_cleanup_cycles": round(sum(self._cleanup_cycles) / max(1, len(self._cleanup_cycles)), 2),
        }


def compute_metrics(run_dir: str | Path) -> RunMetrics:
    """Load all summary JSONs from a run directory and compute metrics."""
    metrics = RunMetrics()
    run_path = Path(run_dir)
    for p in run_path.glob("*_summary.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            summary = RunSummary.model_validate(data)
            metrics.add_summary(summary)
        except Exception:
            continue
    return metrics
