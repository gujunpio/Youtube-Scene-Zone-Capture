"""Service for extracting preview frames and reading video dimensions via FFmpeg/FFprobe."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# On Windows avoid spawning a visible console window for ffmpeg/ffprobe
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def extract_frame(video_path: str, timestamp: float = 0) -> str:
    """Extract a single frame from *video_path* at *timestamp* seconds.

    The frame is saved as ``preview.jpg`` next to the video file.

    Args:
        video_path: Absolute path to the video file.
        timestamp: Time in seconds from which to extract the frame.

    Returns:
        Absolute path to the generated JPEG preview image.

    Raises:
        RuntimeError: If FFmpeg fails.
        FileNotFoundError: If the video file does not exist.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_dir = os.path.dirname(video_path)
    output_path = os.path.join(output_dir, "preview.jpg")

    cmd = [
        "ffmpeg",
        "-ss", str(timestamp),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        "-y",  # overwrite without asking
        output_path,
    ]

    logger.debug("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATION_FLAGS,
    )

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"FFmpeg frame extraction failed (rc={result.returncode}): {stderr_text}")

    if not os.path.isfile(output_path):
        raise RuntimeError("FFmpeg completed but the preview image was not created")

    logger.info("Extracted preview frame at %.2fs → %s", timestamp, output_path)
    return os.path.abspath(output_path)


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """Return the *(width, height)* of the first video stream.

    Uses ``ffprobe`` to inspect the file.

    Args:
        video_path: Absolute path to the video file.

    Returns:
        A tuple ``(width, height)``.

    Raises:
        RuntimeError: If ffprobe fails or returns unexpected output.
        FileNotFoundError: If the video file does not exist.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        video_path,
    ]

    logger.debug("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATION_FLAGS,
    )

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffprobe failed (rc={result.returncode}): {stderr_text}")

    output = result.stdout.decode("utf-8", errors="replace").strip()
    if not output:
        raise RuntimeError("ffprobe returned empty output – is the file a valid video?")

    try:
        parts = output.split(",")
        width = int(parts[0].strip())
        height = int(parts[1].strip())
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Could not parse ffprobe output '{output}': {exc}") from exc

    logger.info("Video dimensions: %dx%d (%s)", width, height, video_path)
    return width, height
