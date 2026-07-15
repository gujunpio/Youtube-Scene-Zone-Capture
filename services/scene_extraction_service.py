"""Service that drives FFmpeg to extract frames from a video at regular intervals."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Callable, Optional

from models.capture_config import CropRect, OutputFormat

logger = logging.getLogger(__name__)

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Regex to match FFmpeg's stderr progress line, e.g. "time=00:02:15.42"
_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def extract(
    video_path: str,
    interval_seconds: float,
    crop_rect: Optional[CropRect],
    output_dir: str,
    output_format: OutputFormat,
    duration: float,
    progress_callback: Optional[Callable[[float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    start_time: float = 0,
    end_time: float = 0,
) -> list[str]:
    """Extract frames from *video_path* at every *interval_seconds*.

    Optionally crops each frame to *crop_rect*.  Progress is reported via
    *progress_callback(percent)* and the extraction can be aborted by having
    *cancel_check()* return ``True``.

    Args:
        video_path: Absolute path to the source video.
        interval_seconds: Seconds between captured frames.
        crop_rect: Optional crop region (``None`` for full-frame).
        output_dir: Directory to write extracted images into.
        output_format: ``OutputFormat.PNG`` or ``OutputFormat.JPG``.
        duration: Total video duration in seconds (used for progress %).
        progress_callback: Called periodically with progress 0–100.
        cancel_check: Return ``True`` to abort.
        start_time: Start time in seconds (default 0).
        end_time: End time in seconds (default 0 = full duration).

    Returns:
        Sorted list of absolute paths to the extracted image files.

    Raises:
        RuntimeError: If FFmpeg exits with an error.
        InterruptedError: If cancelled via *cancel_check*.
    """
    os.makedirs(output_dir, exist_ok=True)

    ext = output_format.value  # "png" or "jpg"

    # Calculate effective duration for progress tracking
    effective_end = end_time if end_time > 0 else duration
    effective_start = max(0, start_time)
    effective_duration = effective_end - effective_start
    if effective_duration <= 0:
        effective_duration = duration

    # Build video-filter chain
    vf_parts: list[str] = []
    if crop_rect is not None:
        vf_parts.append(f"crop={crop_rect.width}:{crop_rect.height}:{crop_rect.x}:{crop_rect.y}")
    vf_parts.append(f"fps=1/{interval_seconds}")
    vf_string = ",".join(vf_parts)

    output_pattern = os.path.join(output_dir, f"%d.{ext}")

    cmd: list[str] = []
    cmd.append("ffmpeg")

    # Seek to start time (before -i for fast seeking)
    if effective_start > 0:
        cmd.extend(["-ss", str(effective_start)])

    cmd.extend(["-i", video_path])

    # Limit duration (process only the selected range)
    if end_time > 0 and end_time < duration:
        cmd.extend(["-t", str(effective_duration)])

    cmd.extend(["-vf", vf_string])

    # Quality flag for JPEG
    if output_format == OutputFormat.JPG:
        cmd.extend(["-q:v", "2"])

    cmd.extend(["-y", output_pattern])

    logger.info("FFmpeg command: %s", " ".join(cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATION_FLAGS,
    )

    # Read stderr line-by-line to track progress
    assert process.stderr is not None
    buf = b""
    try:
        while True:
            # Check cancellation
            if cancel_check and cancel_check():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise InterruptedError("Frame extraction cancelled by user")

            chunk = process.stderr.read(256)
            if not chunk:
                break
            buf += chunk

            # FFmpeg writes progress on the same line using \r
            while b"\r" in buf or b"\n" in buf:
                sep = b"\r" if b"\r" in buf else b"\n"
                line_bytes, buf = buf.split(sep, 1)
                line = line_bytes.decode("utf-8", errors="replace")
                _parse_progress(line, effective_duration, progress_callback)

        # Process remaining buffer
        if buf:
            line = buf.decode("utf-8", errors="replace")
            _parse_progress(line, effective_duration, progress_callback)

    finally:
        process.wait()

    if process.returncode != 0 and not (cancel_check and cancel_check()):
        raise RuntimeError(f"FFmpeg exited with code {process.returncode}")

    # Report 100%
    if progress_callback:
        progress_callback(100.0)

    # Collect and sort output files numerically
    frames = _collect_frames(output_dir, ext)
    logger.info("Extracted %d frames into %s", len(frames), output_dir)
    return frames


def _parse_progress(
    line: str,
    duration: float,
    callback: Optional[Callable[[float], None]],
) -> None:
    """Parse an FFmpeg stderr line for a ``time=`` token and fire *callback*."""
    if not callback or duration <= 0:
        return
    match = _TIME_RE.search(line)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        current = h * 3600 + m * 60 + s
        percent = min(current / duration * 100, 99.9)
        callback(round(percent, 1))


def _collect_frames(directory: str, ext: str) -> list[str]:
    """Return image files in *directory* sorted by their numeric stem."""
    files: list[tuple[int, str]] = []
    for entry in os.listdir(directory):
        name, file_ext = os.path.splitext(entry)
        if file_ext.lstrip(".").lower() == ext.lower():
            try:
                num = int(name)
            except ValueError:
                continue
            files.append((num, os.path.abspath(os.path.join(directory, entry))))
    files.sort(key=lambda t: t[0])
    return [path for _, path in files]
