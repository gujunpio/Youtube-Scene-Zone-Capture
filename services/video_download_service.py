"""Service for downloading videos via yt-dlp with progress reporting."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

import yt_dlp

logger = logging.getLogger(__name__)


def download(
    url: str,
    format_id: str,
    output_dir: str,
    progress_callback: Optional[Callable[[float, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Download a video from *url* into *output_dir*.

    Args:
        url: The video URL (YouTube or any yt-dlp supported site).
        format_id: yt-dlp format selector.  Use ``"best720"`` for a sensible
            default (best video ≤720p merged with best audio).
        output_dir: Directory where the final file will be placed.
        progress_callback: Called with ``(percent, speed_str, eta_str)``
            each time yt-dlp reports progress.
        cancel_check: A zero-arg callable returning *True* when the user
            has requested cancellation.  Checked inside the progress hook.

    Returns:
        Absolute path to the downloaded (merged) video file.

    Raises:
        ValueError: On invalid URL or download failure.
        InterruptedError: If the download is cancelled via *cancel_check*.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Resolve the format string
    if format_id == "best720":
        fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    elif format_id in ("best", ""):
        fmt = "bestvideo+bestaudio/best"
    else:
        # Use the explicit format id; fall back to merging with best audio
        fmt = f"{format_id}+bestaudio/best"

    downloaded_path: Optional[str] = None

    def _progress_hook(d: dict[str, Any]) -> None:
        nonlocal downloaded_path

        # Check cancellation
        if cancel_check and cancel_check():
            raise InterruptedError("Download cancelled by user")

        status = d.get("status")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total * 100) if total else 0.0
            speed_raw = d.get("speed")
            speed = _format_speed(speed_raw) if speed_raw else "-- MiB/s"
            eta_raw = d.get("eta")
            eta = _format_eta(eta_raw) if eta_raw is not None else "--:--"
            if progress_callback:
                progress_callback(round(percent, 1), speed, eta)

        elif status == "finished":
            downloaded_path = d.get("filename")
            if progress_callback:
                progress_callback(100.0, "0 B/s", "00:00")

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    ydl_opts: dict[str, Any] = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "progress_hooks": [_progress_hook],
        "quiet": True,
        "no_warnings": True,
        # Needed for merging on Windows
        "postprocessor_args": {"ffmpeg": ["-loglevel", "quiet"]},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except InterruptedError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise ValueError(f"Download failed: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Unexpected download error: {exc}") from exc

    # If yt-dlp merged, the final filename may differ from what the hook saw
    # (e.g. .webm → .mp4 after merge).  Search the output dir for the result.
    if downloaded_path and os.path.isfile(downloaded_path):
        return os.path.abspath(downloaded_path)

    # Fallback: find the video file in output_dir
    video_path = _find_video_file(output_dir)
    if video_path:
        return video_path

    raise ValueError("Download completed but the output file was not found")


def _find_video_file(directory: str) -> Optional[str]:
    """Return the first video file found in *directory*."""
    video_extensions = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
    for entry in os.listdir(directory):
        if os.path.splitext(entry)[1].lower() in video_extensions:
            return os.path.abspath(os.path.join(directory, entry))
    return None


def _format_speed(bps: float) -> str:
    """Human-readable download speed."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 ** 2:
        return f"{bps / 1024:.1f} KiB/s"
    return f"{bps / 1024 ** 2:.1f} MiB/s"


def _format_eta(seconds: int) -> str:
    """Convert seconds to MM:SS."""
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
