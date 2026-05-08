"""Rich-formatted report generator for Wave 1 run results."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from typing import Literal

from vcl_eval.metrics import RunMetrics


class ReportGenerator:
    """Generates Rich-formatted terminal reports."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def print_summary(self, metrics: RunMetrics) -> None:
        """Print a formatted summary table."""
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]VisionCombatLab — Wave 1 MVP Report[/bold cyan]",
            border_style="cyan",
        ))

        d = metrics.summary_dict()

        table = Table(title="Run Results", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white", justify="right")

        table.add_row("Total Runs", str(d["total_runs"]))
        table.add_row("[green]Cleared[/green]", str(d["cleared_runs"]))
        table.add_row("[red]Failed[/red]", str(d["failed_runs"]))
        table.add_row("[yellow]Stopped[/yellow]", str(d["stopped_runs"]))
        table.add_row("[bold]Clear Rate[/bold]", f"[bold green]{d['clear_rate']:.1%}[/bold green]")
        table.add_row("Mean Clear Time", f"{d['mean_clear_time_sec']:.1f}s")
        self.console.print(table)

        metrics_table = Table(title="Combat Metrics (Averages)", show_header=True)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Avg Value", style="white", justify="right")
        metrics_table.add_row("Radiant Kick Casts", f"{d['mean_radiant_kicks']:.2f}")
        metrics_table.add_row("Observation Scans", f"{d['mean_observation_scans']:.2f}")
        metrics_table.add_row("Cleanup Cycles", f"{d['mean_cleanup_cycles']:.2f}")
        self.console.print(metrics_table)

        safety_table = Table(title="Safety Metrics", show_header=True)
        safety_table.add_column("Metric", style="cyan")
        safety_table.add_column("Value", style="white", justify="right")
        safety_table.add_row("False Exit Attempts", str(d["false_exit_count"]))
        safety_table.add_row("Emergency Stops", str(d["emergency_stop_count"]))

        clear_rate = d["clear_rate"]
        if clear_rate >= 0.9:
            verdict = "[bold green]PASS — 9/10+ clear rate[/bold green]"
        elif clear_rate >= 0.7:
            verdict = "[bold yellow]PARTIAL — 7-8/10 clear rate[/bold yellow]"
        else:
            verdict = "[bold red]FAIL — Below 7/10 clear rate[/bold red]"

        self.console.print(safety_table)
        self.console.print()
        self.console.print(Panel(verdict, border_style="green" if clear_rate >= 0.9 else "yellow"))
        self.console.print()

    def print_run_log(self, log_entries: list[dict]) -> None:
        """Print a formatted run log."""
        table = Table(title="Run Log", show_header=True, header_style="bold blue")
        table.add_column("Time", style="dim", width=8)
        table.add_column("State", style="cyan", width=25)
        table.add_column("Action", style="yellow", width=20)
        table.add_column("Progress", style="green", width=10)
        table.add_column("Reason", style="white")

        for entry in log_entries[-50:]:
            table.add_row(
                f"{entry.get('timestamp', 0):.1f}",
                entry.get("state", ""),
                entry.get("action", ""),
                entry.get("progress", ""),
                str(entry.get("confidence", {})),
            )
        self.console.print(table)
