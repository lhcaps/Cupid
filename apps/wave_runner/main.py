"""Wave Runner CLI — run Wave 1 HSM on video timeline or live."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.panel import Panel

from vcl_core.config import load_config, AppConfig
from vcl_core.logger import RunLogger
from vcl_core.schemas import RunSummary, Wave1Action, Wave1ActionName
from vcl_vision.frame_source import VideoReader, LiveFrameSource
from vcl_vision.progress_detector import ProgressDetector
from vcl_vision.compass_detector import CompassDetector
from vcl_vision.haki_detector import HakiDetector
from vcl_hsm import Wave1HSM, Wave1State
from vcl_input.primitives import InputPrimitives
from vcl_input.executor import InputExecutor
from vcl_input.emergency_stop import EmergencyStop, setup_ctrl_c_handler
from vcl_eval.metrics import RunMetrics, compute_metrics
from vcl_eval.report import ReportGenerator

app = typer.Typer(name="wave-runner", help="Run Wave 1 HSM: dry-run, assist, or execute.")
console = Console()


@app.command()
def simulate(
    timeline: Annotated[Path, typer.Argument(help="Path to timeline.raw.json from replay analyzer")],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    out: Annotated[Path, typer.Option("--out", "-o")] = Path("reports/eval/hsm_dryrun"),
    wave: Annotated[int, typer.Option(help="Wave number")] = 1,
) -> None:
    """
    Run HSM dry-run over a recorded timeline. No key presses.
    Outputs action sequence JSONL for verification.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = _load_config(config)

    timeline_data = json.loads(timeline.read_text(encoding="utf-8"))
    console.print(f"[cyan]Loaded {len(timeline_data)} timeline entries[/cyan]")

    progress_det = ProgressDetector(cfg.progress_ui)
    compass_det = CompassDetector(cfg.compass)
    hsm = Wave1HSM(config=cfg)

    logger = RunLogger(log_dir=out)
    logger.open()

    actions: list[dict] = []
    prev_state = None

    for entry in timeline_data:
        ts = entry.get("timestamp", 0.0)
        state = hsm.state.value

        progress = progress_det._layer_a_check(
            progress_det.config.crop.to_slice()
        ) if False else _fake_progress_from_entry(entry)

        progress_state = progress
        compass_state = _fake_compass_from_entry(entry)

        action = hsm.tick(
            game_state=None,
            progress=progress_state,
            compass=compass_state,
            current_time=ts,
        )

        if state != prev_state or True:
            actions.append({
                "t": round(ts, 2),
                "state": state,
                "action": action.name.value,
                "reason": action.reason,
                "stats": hsm.stats,
            })

        logger.log(
            state=state,
            timestamp=ts,
            progress=(
                f"{progress_state.objective_current}/{progress_state.objective_total}"
                if progress_state.objective_current is not None and progress_state.objective_total is not None
                else "?"
            ),
            compass=compass_state.label,
            action=action,
            progress_confidence=progress_state.confidence,
            compass_confidence=compass_state.confidence,
        )
        prev_state = state

    logger.close()

    actions_path = out / "action_plan.jsonl"
    with actions_path.open("w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")

    if hsm.state == Wave1State.DONE:
        run_status_sim = "clear"
    else:
        run_status_sim = "fail"

    final_progress = hsm._prev_progress
    if final_progress is not None:
        curr = final_progress.objective_current if final_progress.objective_current is not None else None
        total = final_progress.objective_total if final_progress.objective_total is not None else None
        if curr is not None and total is not None:
            objective_final = f"{curr}/{total}"
        elif curr is not None:
            objective_final = f"{curr}/?"
        else:
            objective_final = "?/?"
    else:
        objective_final = "?/?"

    summary = RunSummary(
        run_id=logger.run_id,
        status=run_status_sim,
        duration_sec=timeline_data[-1].get("timestamp", 0) if timeline_data else 0,
        objective_final=objective_final,
        radiant_kick_casts=hsm._radiant_kick_casts,
        observation_scans=hsm._observation_scans,
        cleanup_cycles=hsm._cleanup_cycles,
        failure_reason=None if run_status_sim == "clear" else hsm.state.value,
    )
    logger.log_summary(summary)

    console.print(f"\n[green]HSM dry-run complete![/green]")
    console.print(f"  Actions: {len(actions)}")
    console.print(f"  Final state: {hsm.state.value}")
    console.print(f"  Status: [{run_status_sim}] {run_status_sim.upper()}")
    console.print(f"  Objective final: {objective_final}")
    console.print(f"  Output: {actions_path}")


@app.command()
def live(
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    mode: Annotated[Literal["assist", "execute"], typer.Option("--mode", "-m")] = "assist",
    runs: Annotated[int, typer.Option(help="Number of runs")] = 1,
    stop_on_fail: Annotated[bool, typer.Option(help="Stop runner on first failure")] = True,
) -> None:
    """
    Run Wave 1 live: assist (print actions) or execute (press keys).

    Mode 'assist': prints suggested action only, no key presses.
    Mode 'execute': runs full HSM loop with key presses. REQUIRES explicit --mode execute flag.
    """
    cfg = _load_config(config)
    console.print(Panel.fit(
        f"[bold cyan]Wave 1 Live Runner[/bold cyan] | Mode: [yellow]{mode.upper()}[/yellow]",
        border_style="cyan",
    ))

    progress_det = ProgressDetector(cfg.progress_ui)
    compass_det = CompassDetector(cfg.compass)
    haki_det = HakiDetector(cfg.observation_haki)

    primitives = InputPrimitives(cfg.keybinds)
    executor = InputExecutor(config=cfg, primitives=primitives)
    estop = EmergencyStop(primitives=primitives, screenshot_dir="reports/failure_cases")
    estop.start()
    setup_ctrl_c_handler(primitives, on_stop=lambda: console.print("[red]Stopped by Ctrl+C[/red]"))

    metrics = RunMetrics()

    for run_idx in range(runs):
        run_id = f"wave1_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        console.print(f"\n[cyan]--- Run {run_idx + 1}/{runs} | ID: {run_id} ---[/cyan]")

        logger = RunLogger(run_id=run_id, log_dir="reports/run_logs")
        logger.open()
        hsm = Wave1HSM(config=cfg)
        start_time = time.monotonic()

        run_status: Literal["clear", "fail", "stopped"] = "fail"
        stuck_retries = 0

        try:
            with LiveFrameSource(monitor_index=1, fps_target=cfg.screen.fps_target) as source:
                for ts, frame in source:
                    if estop.is_stopped:
                        run_status = "stopped"
                        break

                    elapsed = time.monotonic() - start_time
                    if elapsed > 60.0:
                        console.print("[yellow]Run timeout: 60s[/yellow]")
                        break

                    progress = progress_det.detect(frame)
                    compass = compass_det.detect(frame)

                    progress_str = (
                        f"{progress.objective_current}/{progress.objective_total}"
                        if progress.objective_current is not None and progress.objective_total is not None
                        else "?"
                    )

                    RISKY_STATES = (
                        Wave1State.VERIFY_STAGE_UI,
                        Wave1State.AGGRO_WITH_GEPPO,
                        Wave1State.CAST_CHARGED_RADIANT_KICK,
                        Wave1State.RELEASE_RADIANT_KICK,
                        Wave1State.VERIFY_COUNTER,
                        Wave1State.ALIGN_TO_EXIT,
                        Wave1State.MOVE_NEXT_STAGE,
                    )

                    if mode == "execute" and hsm.state in RISKY_STATES:
                        if progress.confidence < cfg.progress_ui.min_confidence:
                            console.print(f"  [yellow]!! Low confidence {progress.confidence:.2f} < {cfg.progress_ui.min_confidence:.2f} — skipping hsm.tick, releasing keys[/yellow]")
                            executor.primitives.release_held_keys()
                            logger.log(
                                state=hsm.state.value,
                                timestamp=elapsed,
                                progress=progress_str,
                                compass=compass.label,
                                action=Wave1Action(name=Wave1ActionName.WAIT, reason="low_confidence_paused"),
                                progress_confidence=progress.confidence,
                                compass_confidence=compass.confidence,
                            )
                            continue

                    action = hsm.tick(
                        game_state=None,
                        progress=progress,
                        compass=compass,
                        current_time=elapsed,
                    )

                    console.print(
                        f"  [dim]{elapsed:.1f}s[/dim] [{hsm.state.value}] "
                        f"action={action.name.value} obj={progress_str}"
                    )

                    logger.log(
                        state=hsm.state.value,
                        timestamp=elapsed,
                        progress=progress_str,
                        compass=compass.label,
                        action=action,
                        progress_confidence=progress.confidence,
                        compass_confidence=compass.confidence,
                    )

                    if mode == "execute":
                        executor.execute(action.name)

                    if hsm.state == Wave1State.DONE:
                        run_status = "clear"
                        break

                    if hsm.state == Wave1State.FAILSAFE:
                        run_status = "fail"
                        break

        except KeyboardInterrupt:
            run_status = "stopped"
            estop.trigger()

        duration = time.monotonic() - start_time
        summary = RunSummary(
            run_id=run_id,
            status=run_status,
            duration_sec=round(duration, 1),
            objective_final=(
                f"{hsm._prev_progress.objective_current}/{hsm._prev_progress.objective_total}"
                if hsm._prev_progress and hsm._prev_progress.objective_current is not None and hsm._prev_progress.objective_total is not None
                else "?"
            ),
            radiant_kick_casts=hsm._radiant_kick_casts,
            observation_scans=hsm._observation_scans,
            cleanup_cycles=hsm._cleanup_cycles,
            stuck_retries=stuck_retries,
            failure_reason=None if run_status == "clear" else hsm.state.value,
        )
        logger.log_summary(summary)
        logger.close()
        metrics.add_summary(summary)

        status_color = "green" if run_status == "clear" else "red" if run_status == "fail" else "yellow"
        console.print(f"  [{status_color}]Run {run_idx+1} result: {run_status.upper()}[/{status_color}] | {duration:.1f}s")

        if stop_on_fail and run_status != "clear":
            console.print("[yellow]Stopping on failure (--stop-on-fail)[/yellow]")
            break

    estop.stop()
    console.print("\n[cyan]--- Summary ---[/cyan]")
    reporter = ReportGenerator(console)
    reporter.print_summary(metrics)


@app.command()
def report(
    run_dir: Annotated[Path, typer.Argument(help="Path to run logs directory")] = Path("reports/run_logs"),
) -> None:
    """Generate a formatted report from run logs."""
    console.print(f"[cyan]Loading runs from:[/cyan] {run_dir}")
    metrics = compute_metrics(run_dir)
    reporter = ReportGenerator(console)
    reporter.print_summary(metrics)


@app.command()
def keyboard_test() -> None:
    """Test keyboard input primitives (for manual verification)."""
    console.print("[yellow]Keyboard test — press keys to test, Ctrl+C to exit[/yellow]")
    primitives = InputPrimitives()
    keys_to_test = ["w", "a", "s", "d", "space", "r", "q", "e", "g", "j", "1", "2"]

    def show_held():
        console.print(f"  Held: {sorted(primitives.held_keys)}")

    def on_stop():
        console.print("[red]Stopped[/red]")

    estop = EmergencyStop(primitives=primitives, on_stop=on_stop)
    estop.start()
    setup_ctrl_c_handler(primitives, on_stop=on_stop)

    console.print("[cyan]Test sequence:[/cyan]")
    for key in keys_to_test:
        console.print(f"  Tapping {key}...", end=" ")
        primitives.tap(key, down_ms=200)
        console.print("[green]OK[/green]")
        show_held()
        time.sleep(0.3)

    console.print("[green]All keys tested successfully![/green]")
    estop.stop()


def _load_config(config: Path | None) -> AppConfig:
    if config and config.exists():
        return load_config(config)
    default_path = Path("configs/wave1.shattered_ramparts.yaml")
    if default_path.exists():
        return load_config(default_path)
    return AppConfig()


def _fake_progress_from_entry(entry: dict) -> "ProgressState":
    from vcl_vision.progress_detector import ProgressState
    return ProgressState(
        stage_name=entry.get("stage_name"),
        objective_current=entry.get("objective_current"),
        objective_total=entry.get("objective_total"),
        confidence=entry.get("progress_confidence", 0.0),
    )


def _fake_compass_from_entry(entry: dict) -> "CompassState":
    from vcl_vision.compass_detector import CompassState
    return CompassState(
        label=entry.get("compass_label"),
        angle_deg=entry.get("compass_angle_deg"),
        confidence=entry.get("compass_confidence", 0.0),
    )


if __name__ == "__main__":
    app()
