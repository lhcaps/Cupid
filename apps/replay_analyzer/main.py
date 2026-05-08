"""Replay Analyzer CLI — analyze video, extract frames, generate contact sheet."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import typer
from rich.console import Console
from rich.progress import track

from vcl_core.config import load_config, AppConfig
from vcl_vision.frame_source import VideoReader
from vcl_vision.progress_detector import ProgressDetector
from vcl_vision.compass_detector import CompassDetector
from vcl_vision.debug_render import DebugRenderer

app = typer.Typer(name="replay-analyzer", help="Analyze gameplay video for Wave 1 replay.")
console = Console()


@app.command()
def analyze(
    video: Annotated[Path, typer.Argument(help="Path to input video file (.mp4)")],
    config: Annotated[Path | None, typer.Option("--config", "-c", help="YAML config path")] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("reports/eval/replay"),
    interval: Annotated[float, typer.Option(help="Frame sampling interval in seconds")] = 1.0,
    debug: Annotated[bool, typer.Option("--debug", help="Generate annotated debug frames")] = False,
) -> None:
    """
    Analyze a gameplay video and produce:
    - metadata.json (fps, resolution, duration)
    - frames/ (sampled frames at interval)
    - contact_sheet.jpg (grid of sampled frames)
    - timeline.raw.json (frame timestamps + progress/compass data)
    - progress_samples.jsonl (per-frame progress detector output)
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    frames_dir = out / "frames_sampled"
    frames_dir.mkdir(exist_ok=True)

    cfg: AppConfig
    if config and config.exists():
        cfg = load_config(config)
        console.print(f"[cyan]Loaded config:[/cyan] {config}")
    else:
        cfg = AppConfig()
        console.print("[yellow]Using default config (no config provided)[/yellow]")

    console.print(f"[cyan]Opening video:[/cyan] {video}")
    try:
        vr = VideoReader(video)
    except Exception as e:
        console.print(f"[red]Error opening video:[/red] {e}")
        raise typer.Exit(1)

    metadata = vr.metadata
    console.print(f"[green]Video info:[/green]")
    console.print(f"  FPS: {metadata['fps']:.1f}")
    console.print(f"  Resolution: {metadata['width']}x{metadata['height']}")
    console.print(f"  Duration: {metadata['duration_sec']:.1f}s")
    console.print(f"  Frames: {metadata['frame_count']}")

    metadata_path = out / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    progress_det = ProgressDetector(cfg.progress_ui)
    compass_det = CompassDetector(cfg.compass)
    renderer = DebugRenderer() if debug else None

    timeline: list[dict] = []
    progress_samples: list[dict] = []
    frame_count = 0
    saved_count = 0

    console.print(f"[cyan]Sampling frames every {interval}s...[/cyan]")

    for ts, frame in vr.iter_sampled(interval):
        frame_count += 1

        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            continue

        progress = progress_det.detect(frame)
        compass = compass_det.detect(frame)

        sample_entry = {
            "timestamp": round(ts, 3),
            "frame_index": frame_count,
            "stage_name": progress.stage_name,
            "objective_current": progress.objective_current,
            "objective_total": progress.objective_total,
            "progress_confidence": progress.confidence,
            "compass_label": compass.label,
            "compass_angle_deg": compass.angle_deg,
            "compass_confidence": compass.confidence,
        }
        timeline.append(sample_entry)

        if frame_count % 10 == 0:
            progress_samples.append(sample_entry)

        if saved_count < 200:
            frame_path = frames_dir / f"frame_{frame_count:06d}_{ts:.2f}s.jpg"
            cv2.imwrite(str(frame_path), frame)
            saved_count += 1

            if debug and renderer:
                annotated = renderer.render(
                    frame, progress=progress, compass=compass,
                    current_state="REPLAY_ANALYSIS",
                )
                debug_path = out / "debug_videos" / f"debug_{frame_count:06d}.jpg"
                debug_path.parent.mkdir(exist_ok=True)
                cv2.imwrite(str(debug_path), annotated)

        if frame_count % 30 == 0:
            obj = f"{progress.objective_current or '?'}/{progress.objective_total or '?'}"
            console.print(
                f"  [dim]t={ts:.1f}s[/dim] stage={progress.stage_name or '?'} "
                f"obj={obj} conf={progress.confidence:.2f} "
                f"compass={compass.label or '?'}"
            )

    vr.close()

    timeline_path = out / "timeline.raw.json"
    timeline_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")

    samples_path = out / "progress_samples.jsonl"
    with samples_path.open("w", encoding="utf-8") as f:
        for sample in progress_samples:
            f.write(json.dumps(sample) + "\n")

    _create_contact_sheet(frames_dir, out, max_grid=400)

    console.print(f"\n[green]Analysis complete![/green]")
    console.print(f"  Frames sampled: {frame_count}")
    console.print(f"  Saved to: {out}")
    console.print(f"  Timeline: {timeline_path}")
    console.print(f"  Samples: {samples_path}")


def _create_contact_sheet(frames_dir: Path, out_dir: Path, max_grid: int = 400) -> None:
    """Create a contact sheet grid from saved frames."""
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        return

    cols = min(10, len(frames))
    rows = (len(frames) + cols - 1) // cols
    if rows * cols > max_grid:
        cols = max(1, int(max_grid / rows))
        rows = (len(frames) + cols - 1) // cols

    sample_frames = frames[: rows * cols]

    thumb_w, thumb_h = 320, 180
    sheet = np.zeros((rows * thumb_h, cols * thumb_w, 3), dtype=np.uint8)

    for idx, fp in enumerate(sample_frames):
        row = idx // cols
        col = idx % cols
        frame = cv2.imread(str(fp))
        if frame is None:
            continue
        thumb = cv2.resize(frame, (thumb_w, thumb_h))
        y0, y1 = row * thumb_h, (row + 1) * thumb_h
        x0, x1 = col * thumb_w, (col + 1) * thumb_w
        sheet[y0:y1, x0:x1] = thumb

    sheet_path = out_dir / "contact_sheet.jpg"
    cv2.imwrite(str(sheet_path), sheet)
    console.print(f"  [cyan]Contact sheet:[/cyan] {sheet_path} ({rows}x{cols})")


if __name__ == "__main__":
    app()
