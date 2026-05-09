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
from vcl_input.backends import create_input_backend, LoggingInputBackend, InputBackend
from vcl_input.window_focus import ensure_window_focused, get_active_window_title
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
    capture_backend: Annotated[str | None, typer.Option("--capture-backend")] = None,
    input_backend: Annotated[str | None, typer.Option("--input-backend")] = None,
    debug_input: Annotated[bool, typer.Option("--debug-input/--no-debug-input")] = False,
    debug_vision: Annotated[bool, typer.Option("--debug-vision/--no-debug-vision")] = False,
    input_preflight: Annotated[bool, typer.Option("--input-preflight/--no-input-preflight")] = True,
) -> None:
    """
    Run Wave 1 live: assist (print actions) or execute (press keys).

    ASSIST MODE:  prints suggested action only, no key presses. Safe for diagnosis.
    EXECUTE MODE: runs full HSM loop with key presses. REQUIRES explicit --mode execute flag.

    Runtime backend flags:
      --capture-backend [mss|dxcam]   : Screen capture backend (default: mss)
      --input-backend [pynput|pydirectinput|pyautogui] : Keyboard backend (default: pynput)
      --debug-input                     : Log executor queue, held keys, backend name
      --debug-vision                    : Save crop snapshots to reports/vision_debug/
      --input-preflight                 : Validate input backend before live loop (execute mode default: true)
    """
    cfg = _load_config(config)

    # Apply CLI overrides
    if capture_backend is not None:
        cfg.capture.backend = capture_backend
    if input_backend is not None:
        cfg.input.backend = input_backend
    if debug_input:
        cfg.debug.input = True
    if debug_vision:
        cfg.debug.vision = True

    if mode == "assist":
        console.print(Panel.fit(
            "[bold cyan]ASSIST MODE[/bold cyan] — [yellow]NO KEYPRESSES[/yellow], "
            "HSM/vision diagnosis only. Safe to run anytime.",
            border_style="cyan",
        ))
        _print_runtime_info(cfg, mode)
    else:
        console.print(Panel.fit(
            "[bold red]EXECUTE MODE[/bold red] — [yellow]REAL KEYPRESSES WILL BE SENT.[/yellow] "
            "Ensure Roblox window is focused.",
            border_style="red",
        ))
        _print_runtime_info(cfg, mode)
        _preflight_input(cfg, console, input_preflight, mode)

    progress_det = ProgressDetector(cfg.progress_ui)
    compass_det = CompassDetector(cfg.compass)
    haki_det = HakiDetector(cfg.observation_haki)

    # Create input backend and primitives. Assist uses LoggingInputBackend (no real input).
    # Execute uses the selected backend (validated in preflight).
    if mode == "assist":
        runtime_input_backend: "InputBackend | None" = None  # LoggingInputBackend injected below
        primitives = InputPrimitives(
            keybinds=cfg.keybinds,
            input_config=cfg.input,
            backend=LoggingInputBackend(),
        )
    else:
        runtime_input_backend = create_input_backend(cfg.input)
        primitives = InputPrimitives(
            keybinds=cfg.keybinds,
            input_config=cfg.input,
            backend=runtime_input_backend,
        )
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

        RISKY_STATES = (
            # VERIFY_STAGE_UI intentionally excluded: HSM must tick through it to
            # reach AGGRO_WITH_GEPPO even with low-confidence 0/4 initial reads.
            # No combat actions are taken in VERIFY_STAGE_UI so blocking it would
            # deadlock the runner before combat even starts.
            Wave1State.AGGRO_WITH_GEPPO,
            Wave1State.CAST_CHARGED_RADIANT_KICK,
            Wave1State.RELEASE_RADIANT_KICK,
            Wave1State.VERIFY_COUNTER,
            Wave1State.ALIGN_TO_EXIT,
            Wave1State.MOVE_NEXT_STAGE,
        )

        prev_state: str | None = None

        try:
            with LiveFrameSource(
                monitor_index=cfg.capture.monitor_index,
                fps_target=cfg.capture.fps_target,
                region=cfg.capture.region.to_dict() if cfg.capture.region else None,
                backend=cfg.capture.backend,
            ) as source:
                console.print(f"  [dim]Capture backend: {source.backend_name}[/dim]")
                console.print(f"  [dim]Input backend  : {primitives.backend_name}[/dim]")

                # Create VisionDebug once per run, not per frame
                vision_debugger: "VisionDebug | None" = None
                if cfg.debug.vision:
                    from vcl_vision.vision_debug import VisionDebug
                    vision_debugger = VisionDebug(run_id, cfg.debug)

                for ts, frame in source:
                    if estop.is_stopped:
                        run_status = "stopped"
                        break

                    elapsed = time.monotonic() - start_time
                    if elapsed > 60.0:
                        console.print("[yellow]Run timeout: 60s[/yellow]")
                        run_status = "fail"
                        break

                    progress, debug_info = progress_det.detect_with_debug(frame)
                    compass = compass_det.detect(frame)

                    progress_str = (
                        f"{progress.objective_current}/{progress.objective_total}"
                        if progress.objective_current is not None and progress.objective_total is not None
                        else "?"
                    )

                    # Debug vision: save crops on cadence
                    if vision_debugger is not None and debug_info is not None:
                        h, w = frame.shape[:2]
                        cfg_ = progress_det.config
                        x1, y1 = cfg_.crop.x1, cfg_.crop.y1
                        x2, y2 = min(cfg_.crop.x2, w), min(cfg_.crop.y2, h)
                        prog_crop = frame[y1:y2, x1:x2] if x1 < x2 and y1 < y2 else frame
                        cx1, cy1 = cfg_.counter_crop.x1, cfg_.counter_crop.y1
                        cx2, cy2 = min(cfg_.counter_crop.x2, w), min(cfg_.counter_crop.y2, h)
                        cnt_crop = frame[cy1:cy2, cx1:cx2] if cx1 < cx2 and cy1 < cy2 else frame
                        vision_debugger.save_frame(
                            ts=elapsed,
                            frame=frame,
                            progress_crop=prog_crop,
                            counter_crop=cnt_crop,
                            debug_info={
                                "mode": debug_info.selected_mode,
                                "candidates": debug_info.candidate_count,
                                "slots": debug_info.slot_count,
                                "circle_count": debug_info.circle_count,
                                "circle_conf": debug_info.circle_conf,
                                "text_count": debug_info.text_count,
                                "text_conf": debug_info.text_conf,
                                "panel_active": debug_info.panel_active,
                                "panel_conf": debug_info.panel_conf,
                                "raw_confidence": debug_info.raw_confidence,
                                "objective_current": progress.objective_current,
                                "objective_total": progress.objective_total,
                                "progress_confidence": progress.confidence,
                            },
                        )

                    low_conf = progress.confidence < cfg.progress_ui.min_confidence
                    in_risky = hsm.state in RISKY_STATES

                    if mode == "execute" and low_conf and in_risky:
                        console.print(
                            f"  [yellow]!! Low conf {progress.confidence:.2f} < "
                            f"{cfg.progress_ui.min_confidence:.2f} in risky state "
                            f"[{hsm.state.value}] — releasing keys[/yellow]"
                        )
                        if cfg.debug.input:
                            console.print(
                                f"    [dim]executor queue={len(executor._queue)} "
                                f"held={sorted(primitives.held_keys)}[/dim]"
                            )
                        executor.primitives.release_held_keys()
                        logger.log(
                            state=hsm.state.value,
                            timestamp=elapsed,
                            progress=progress_str,
                            compass=compass.label,
                            action=Wave1Action(name=Wave1ActionName.WAIT, reason="low_confidence_pre_hsm_pause"),
                            progress_confidence=progress.confidence,
                            compass_confidence=compass.confidence,
                        )
                        executor.tick()
                        continue

                    action = hsm.tick(
                        game_state=None,
                        progress=progress,
                        compass=compass,
                        current_time=elapsed,
                    )

                    # Debug input: log executor state on non-WAIT actions
                    if cfg.debug.input and action.name != Wave1ActionName.WAIT:
                        console.print(
                            f"  [dim]{elapsed:.1f}s[/dim] [{hsm.state.value}] "
                            f"[INPUT DEBUG] action={action.name.value} "
                            f"backend={primitives.backend_name} "
                            f"queue={len(executor._queue)} "
                            f"held={sorted(primitives.held_keys)}"
                        )

                    console.print(
                        f"  [dim]{elapsed:.1f}s[/dim] [{hsm.state.value}] "
                        f"action={action.name.value} obj={progress_str} "
                        f"pconf={progress.confidence:.2f} cc={compass.confidence:.2f}"
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

                    if mode == "execute":
                        executor.tick()

                    # State transition debug snapshot
                    if cfg.debug.vision and hsm.state.value != prev_state:
                        prev_state = hsm.state.value

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


def _print_runtime_info(cfg: AppConfig, mode: str) -> None:
    """Print configured runtime backends."""
    console.print(f"  Capture backend : {cfg.capture.backend}")
    console.print(f"  Input backend   : {cfg.input.backend}")
    console.print(f"  Focus window   : {cfg.input.focus_window_title!r}")
    console.print(f"  Require focus  : {cfg.input.require_focus}")
    console.print(f"  Fail on error  : {cfg.input.fail_on_input_error}")
    if mode == "execute":
        console.print(f"  Debug input    : {cfg.debug.input}")
    console.print(f"  Debug vision   : {cfg.debug.vision}")


def _preflight_input(
    cfg: AppConfig,
    console: Console,
    preflight_enabled: bool,
    mode: str,
) -> None:
    """Preflight check: validate window focus and input backend before live loop."""
    if mode == "assist":
        console.print("[dim]  [SKIP] Preflight not required in assist mode[/dim]")
        return

    if not preflight_enabled:
        console.print("[dim]  [SKIP] Preflight disabled[/dim]")
        return

    # Check window focus
    title = cfg.input.focus_window_title
    require = cfg.input.require_focus

    try:
        focused, msg = ensure_window_focused(title, require=False)
        if not focused and require:
            console.print(f"[red]  Window focus check FAILED: {msg}[/red]")
            console.print("[red]  EXECUTE ABORTED: require_focus=true but window is not focused.[/red]")
            console.print("[red]  Bring Roblox to foreground and retry, or use --no-input-preflight to skip.[/red]")
            raise typer.Exit(code=2)
        elif focused:
            console.print(f"  [green]Window focus: OK ({msg})[/green]")
        else:
            console.print(f"  [yellow]Window focus: {msg} (require_focus=false, proceeding)[/yellow]")
    except RuntimeError as e:
        if require:
            console.print(f"[red]  Window focus guard unavailable: {e}[/red]")
            console.print("[red]  EXECUTE ABORTED: require_focus=true but PyWinCtl is not installed.[/red]")
            console.print("[red]  Install with: pip install PyWinCtl[/red]")
            raise typer.Exit(code=2)
        console.print(f"  [yellow]Window focus skipped (PyWinCtl unavailable): {e}[/yellow]")

    # Validate input backend instantiation
    console.print(f"  [dim]Validating input backend: {cfg.input.backend}...[/dim]")
    try:
        backend = create_input_backend(cfg.input)
        console.print(f"  [green]Input backend: {backend.name} (instantiated OK)[/green]")
    except Exception as e:
        console.print(f"[red]  Input backend FAILED: {e}[/red]")
        raise typer.Exit(code=2)


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
def keyboard_test(
    input_backend: Annotated[str | None, typer.Option("--input-backend")] = None,
) -> None:
    """
    Test keyboard input backend (for manual verification).

    This will press real keys. Ensure Roblox is focused before running.
    Use --input-backend to select: pynput (default), pydirectinput, pyautogui
    """
    from vcl_input.backends import create_input_backend
    from vcl_core.config import InputConfig

    cfg = _load_config(None)
    if input_backend is not None:
        cfg.input.backend = input_backend

    backend_name = cfg.input.backend
    console.print(f"[yellow]Keyboard test — backend: {backend_name}[/yellow]")
    console.print("[yellow]Press Ctrl+C to exit[/yellow]")

    backend = create_input_backend(cfg.input)
    console.print(f"  Backend: {backend.name}")
    keys_to_test = ["w", "a", "s", "d", "space", "r", "q", "e", "g", "j", "1", "2"]

    console.print("[cyan]Test sequence:[/cyan]")
    for key in keys_to_test:
        console.print(f"  Tapping {key}...", end=" ")
        try:
            backend.press(key)
            time.sleep(0.15)
            backend.release(key)
            console.print("[green]OK[/green]")
        except Exception as e:
            console.print(f"[red]FAILED: {e}[/red]")
        time.sleep(0.3)

    console.print("[green]All keys tested successfully![/green]")
    backend.close()


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
