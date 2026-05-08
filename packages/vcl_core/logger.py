"""JSONL logger for VisionCombatLab run logs."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import IO

from .schemas import RunLogEntry, RunSummary, Wave1Action


class RunLogger:
    """Appends JSONL log entries for a single Wave 1 run."""

    def __init__(self, run_id: str | None = None, log_dir: str | Path | None = None) -> None:
        self.run_id = run_id or f"wave1_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.log_dir = Path(log_dir) if log_dir else Path("reports/run_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._file: IO[str] | None = None
        self._entry_count = 0

    @property
    def log_path(self) -> Path:
        return self.log_dir / f"{self.run_id}.jsonl"

    def open(self) -> "RunLogger":
        if self._file is None:
            self._file = open(self.log_path, "w", encoding="utf-8")
        return self

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def log(
        self,
        state: str,
        timestamp: float,
        progress: str | None,
        compass: str | None,
        action: Wave1Action | str,
        **confidence_kwargs: float,
    ) -> None:
        action_name = action.name if isinstance(action, Wave1Action) else str(action)
        entry = RunLogEntry(
            run_id=self.run_id,
            state=state,
            timestamp=timestamp,
            progress=progress,
            compass=compass,
            action=action_name,
            confidence=confidence_kwargs,
        )
        self._write_entry(entry)
        self._entry_count += 1

    def log_summary(self, summary: RunSummary) -> None:
        path = self.log_dir / f"{self.run_id}_summary.json"
        path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    def _write_entry(self, entry: RunLogEntry) -> None:
        if self._file is None:
            self.open()
        line = entry.model_dump_json()
        self._file.write(line + "\n")  # type: ignore
        self._file.flush()  # type: ignore

    def __enter__(self) -> "RunLogger":
        return self.open()

    def __exit__(self, *_: object) -> None:
        self.close()


def read_run_logs(log_dir: str | Path) -> list[RunLogEntry]:
    """Read all JSONL entries from a log directory."""
    entries: list[RunLogEntry] = []
    for p in Path(log_dir).glob("*.jsonl"):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(RunLogEntry.model_validate_json(line))
    return entries
