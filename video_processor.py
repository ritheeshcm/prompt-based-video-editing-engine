"""
PS2 — FFmpeg Video Processor
Executes actual video edits using FFmpeg subprocess calls.
"""

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from app.prompt_parser import EditOperation, ParseResult


def _find_ffmpeg() -> str:
    """Find ffmpeg binary — checks PATH first, then common Windows install paths."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        str(Path.home() / "scoop" / "shims" / "ffmpeg.exe"),
    ]

    winget_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_base.exists():
        for pkg in winget_base.iterdir():
            if "ffmpeg" in pkg.name.lower() or "gyan" in pkg.name.lower():
                for ffmpeg_exe in pkg.rglob("ffmpeg.exe"):
                    candidates.append(str(ffmpeg_exe))

        # Also cover the default WinGet FFmpeg package layout.
        for ffmpeg_exe in winget_base.glob("**/ffmpeg.exe"):
            candidates.append(str(ffmpeg_exe))

    for path in candidates:
        if Path(path).exists():
            return str(Path(path).resolve())

    return "ffmpeg"  # Fallback — will raise if not found


FFMPEG_BIN = _find_ffmpeg()
FFPROBE_BIN = shutil.which("ffprobe") or str(Path(FFMPEG_BIN).with_name("ffprobe.exe"))


class VideoProbeError(RuntimeError):
    """Raised when FFprobe cannot read a valid video file."""


def check_ffmpeg() -> dict:
    """Check if FFmpeg is available and return version info."""
    try:
        result = subprocess.run(
            [FFMPEG_BIN, "-version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {
                "available": False,
                "error": result.stderr.strip() or f"FFmpeg exited with code {result.returncode}.",
                "path": FFMPEG_BIN,
            }
        version_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
        probe_available = Path(FFPROBE_BIN).exists() or shutil.which(FFPROBE_BIN) is not None
        return {
            "available": True,
            "version": version_line,
            "path": FFMPEG_BIN,
            "ffprobe_available": probe_available,
            "ffprobe_path": FFPROBE_BIN,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"available": False, "error": str(e), "path": FFMPEG_BIN}


def probe_video(input_path: str) -> dict:
    """Return verified video metadata, or raise a useful error for invalid input."""
    try:
        result = subprocess.run(
            [
                FFPROBE_BIN,
                "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,codec_name,width,height",
                "-of", "json",
                input_path,
            ],
            capture_output=True, text=True, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise VideoProbeError(f"Could not inspect video with FFprobe: {e}") from e
    if result.returncode != 0:
        detail = result.stderr.strip() or "FFprobe could not read this file."
        raise VideoProbeError(detail[-1000:])

    try:
        info = json.loads(result.stdout)
        video_stream = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
        duration = float(info["format"]["duration"])
        width = int(video_stream["width"])
        height = int(video_stream["height"])
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as e:
        raise VideoProbeError("The uploaded file has no valid video stream or duration.") from e
    if duration <= 0 or width <= 0 or height <= 0:
        raise VideoProbeError("The uploaded file has invalid video dimensions or duration.")

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": any(stream.get("codec_type") == "audio" for stream in info["streams"]),
        "video_codec": video_stream.get("codec_name"),
    }


def get_video_duration(input_path: str) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    try:
        return probe_video(input_path)["duration"]
    except VideoProbeError:
        return None


def build_ffmpeg_command(
    input_path: str,
    output_path: str,
    operations: list[EditOperation],
    video_duration: Optional[float] = None,
    has_audio: bool = True,
) -> list[str]:
    """
    Build a single FFmpeg command that applies all operations in one pass.
    One-pass = faster processing and no quality loss from re-encoding multiple times.
    """
    trim = next((op for op in operations if op.operation == "trim"), None)
    start = 0.0
    trim_duration: Optional[float] = None
    if trim:
        if "from_end" in trim.params:
            if video_duration is None:
                raise VideoProbeError("Video duration is required to keep the last part of a video.")
            keep_duration = float(trim.params["from_end"])
            if keep_duration <= 0:
                raise ValueError("The duration to keep must be greater than zero.")
            trim_duration = min(keep_duration, video_duration)
            start = video_duration - trim_duration
        else:
            start = float(trim.params.get("start", 0))
            end = float(trim.params.get("end", video_duration)) if video_duration is not None else None
            if start < 0 or end is None or end <= start:
                raise ValueError("Trim range must have a non-negative start and an end after the start.")
            if video_duration is not None:
                if start >= video_duration:
                    raise ValueError("Trim start is beyond the end of the uploaded video.")
                end = min(end, video_duration)
            trim_duration = end - start
    speed = next((op for op in operations if op.operation == "speed"), None)
    if trim_duration is not None and speed:
            speed_factor = float(speed.params["factor"])
            if speed_factor <= 0:
                raise ValueError("Speed factor must be greater than zero.")
            trim_duration /= speed_factor

    cmd = [FFMPEG_BIN, "-y", "-progress", "pipe:1", "-nostats"]
    if start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    cmd += ["-i", input_path]
    if trim_duration is not None:
        cmd += ["-t", f"{trim_duration:.6f}"]

    vf_filters = []
    af_filters = []
    muted = any(op.operation == "mute" for op in operations)
    aspect_operation = next((op for op in operations if op.operation == "aspect_ratio"), None)
    resolution_operation = next((op for op in operations if op.operation == "resolution"), None)
    target_dimensions = None
    if aspect_operation:
        target_dimensions = (
            int(aspect_operation.params["width"]),
            int(aspect_operation.params["height"]),
        )
        if resolution_operation:
            target_ratio = target_dimensions[0] / target_dimensions[1]
            long_edge = max(
                int(resolution_operation.params["width"]),
                int(resolution_operation.params["height"]),
            )
            if target_ratio >= 1:
                target_dimensions = (long_edge, round(long_edge / target_ratio))
            else:
                target_dimensions = (round(long_edge * target_ratio), long_edge)

    for op in operations:
        if op.operation == "trim":
            continue

        elif op.operation == "volume":
            factor = op.params.get("factor", 1.0)
            if has_audio and not muted:
                af_filters.append(f"volume={factor}")

        elif op.operation == "aspect_ratio":
            width, height = target_dimensions or (op.params["width"], op.params["height"])
            # Pad to target ratio without stretching (preserves original content)
            vf_filters.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
            )

        elif op.operation == "speed":
            factor = op.params["factor"]
            # Video: setpts (inverse of speed factor)
            pts_factor = round(1.0 / factor, 4)
            vf_filters.append(f"setpts={pts_factor}*PTS")
            # Audio: atempo supports 0.5–2.0 only, chain for extremes
            if has_audio and not muted:
                if 0.5 <= factor <= 2.0:
                    af_filters.append(f"atempo={factor}")
                elif factor > 2.0:
                    # Chain: e.g. 4x = atempo=2.0,atempo=2.0
                    remaining = factor
                    while remaining > 2.0:
                        af_filters.append("atempo=2.0")
                        remaining /= 2.0
                    if remaining > 1.0:
                        af_filters.append(f"atempo={round(remaining, 4)}")
                else:
                    # Slow: factor < 0.5
                    remaining = factor
                    while remaining < 0.5:
                        af_filters.append("atempo=0.5")
                        remaining *= 2.0
                    if remaining < 1.0:
                        af_filters.append(f"atempo={round(remaining, 4)}")

        elif op.operation == "rotate":
            angle = op.params["angle"]
            if angle == "hflip":
                vf_filters.append("hflip")
            elif angle == "vflip":
                vf_filters.append("vflip")
            elif angle == 90:
                vf_filters.append("transpose=1")
            elif angle == 180:
                vf_filters.append("transpose=1,transpose=1")
            elif angle == 270:
                vf_filters.append("transpose=2")

        elif op.operation == "resolution":
            if aspect_operation:
                continue
            w = op.params["width"]
            h = op.params["height"]
            vf_filters.append(f"scale={w}:{h}")

        elif op.operation == "grayscale":
            vf_filters.append("hue=s=0")

    # ── Assemble filters ─────────────────────────────────────────────────────
    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]
    if af_filters and has_audio:
        cmd += ["-af", ",".join(af_filters)]

    cmd += ["-map", "0:v:0"]
    if has_audio and not muted:
        cmd += ["-map", "0:a?"]
    else:
        cmd += ["-an"]

    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-fps_mode", "vfr",
    ]
    if has_audio and not muted:
        cmd += ["-c:a", "aac", "-b:a", "128k"]

    cmd += ["-movflags", "+faststart"]
    cmd.append(output_path)
    return cmd


def _expected_output_duration(
    operations: list[EditOperation],
    video_duration: float,
) -> float:
    duration = video_duration
    trim = next((op for op in operations if op.operation == "trim"), None)
    if trim:
        if "from_end" in trim.params:
            duration = min(float(trim.params["from_end"]), video_duration)
        else:
            start = float(trim.params.get("start", 0))
            end = float(trim.params.get("end", video_duration))
            duration = min(end, video_duration) - start
    for operation in operations:
        if operation.operation == "speed":
            duration /= float(operation.params["factor"])
    return duration


def process_video(
    input_path: str,
    output_path: str,
    parse_result: ParseResult,
    progress_callback=None,
) -> dict:
    """
    Run FFmpeg to process the video.
    Returns a dict with: success, output_path, error, command_used
    """
    if not parse_result.understood:
        return {
            "success": False,
            "error": " ".join(parse_result.warnings) or "Could not safely understand the requested operations.",
            "command_used": [],
        }
    if not parse_result.operations:
        return {
            "success": False,
            "error": "No operations to perform.",
            "command_used": []
        }

    try:
        metadata = probe_video(input_path)
        if not metadata["has_audio"] and any(
            operation.operation == "volume" for operation in parse_result.operations
        ):
            raise ValueError("Cannot adjust volume because the uploaded video has no audio track.")
        cmd = build_ffmpeg_command(
            input_path,
            output_path,
            parse_result.operations,
            metadata["duration"],
            metadata["has_audio"],
        )
    except (OSError, ValueError, VideoProbeError) as e:
        return {"success": False, "error": str(e), "command_used": []}

    output_duration = _expected_output_duration(parse_result.operations, metadata["duration"])
    output_lines: queue.Queue[str | None] = queue.Queue()
    stderr_lines: deque[str] = deque(maxlen=100)
    timed_out = False
    return_code: Optional[int] = None

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"FFmpeg not found at '{FFMPEG_BIN}'. Install FFmpeg and FFprobe or add them to PATH.",
            "command_used": cmd,
        }

    def read_progress() -> None:
        if process.stdout is not None:
            for line in process.stdout:
                output_lines.put(line.rstrip())
        output_lines.put(None)

    def read_errors() -> None:
        if process.stderr is not None:
            for line in process.stderr:
                stderr_lines.append(line.rstrip())

    stdout_thread = threading.Thread(target=read_progress, daemon=True)
    stderr_thread = threading.Thread(target=read_errors, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    started_at = time.monotonic()
    current_output_time = 0.0
    last_reported_progress = 39
    stdout_finished = False
    if progress_callback:
        progress_callback("FFmpeg is processing the video...", 40)

    while not stdout_finished or process.poll() is None:
        if time.monotonic() - started_at > 300:
            timed_out = True
            process.kill()
            break
        try:
            line = output_lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if line is None:
            stdout_finished = True
        elif line.startswith("out_time_us="):
            try:
                current_output_time = int(line.partition("=")[2]) / 1_000_000
            except ValueError:
                continue
        elif line.startswith("progress=") and progress_callback and output_duration > 0:
            progress = min(99, 40 + int(59 * current_output_time / output_duration))
            if progress > last_reported_progress:
                progress_callback("FFmpeg is processing the video...", progress)
                last_reported_progress = progress

    return_code = process.wait()
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    stderr = "\n".join(stderr_lines)

    if timed_out:
        Path(output_path).unlink(missing_ok=True)
        return {
            "success": False,
            "error": "FFmpeg timed out after 5 minutes.",
            "stderr": stderr[-3000:],
            "command_used": cmd,
        }

    if return_code != 0:
        Path(output_path).unlink(missing_ok=True)
        return {
            "success": False,
            "error": f"FFmpeg failed with code {return_code}.",
            "stderr": stderr[-3000:],
            "command_used": cmd,
        }

    try:
        file_size = Path(output_path).stat().st_size
        if file_size == 0:
            raise VideoProbeError("FFmpeg produced an empty output file.")
        output_metadata = probe_video(output_path)
    except (OSError, VideoProbeError) as e:
        Path(output_path).unlink(missing_ok=True)
        return {
            "success": False,
            "error": f"FFmpeg output validation failed: {e}",
            "stderr": stderr[-3000:],
            "command_used": cmd,
        }

    return {
        "success": True,
        "output_path": output_path,
        "file_size_bytes": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "metadata": output_metadata,
        "command_used": cmd,
        "stderr": stderr[-2000:],
    }
