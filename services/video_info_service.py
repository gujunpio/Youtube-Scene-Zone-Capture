"""Service for fetching video metadata from a URL using yt-dlp."""

from __future__ import annotations

import logging
from typing import Any

import yt_dlp

from models.capture_config import VideoFormat, VideoInfo

logger = logging.getLogger(__name__)


def get_info(url: str) -> VideoInfo:
    """Retrieve video metadata without downloading.

    Args:
        url: A YouTube (or other yt-dlp supported) video URL.

    Returns:
        A VideoInfo object with title, duration, thumbnail, and available formats.

    Raises:
        ValueError: If the URL is invalid, the video is private/deleted, or
                     metadata extraction fails for any reason.
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Don't actually download anything
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).lower()
        if "private" in msg:
            raise ValueError(f"This video is private and cannot be accessed: {url}") from exc
        if "removed" in msg or "deleted" in msg or "not available" in msg:
            raise ValueError(f"This video has been deleted or is unavailable: {url}") from exc
        if "not a valid url" in msg or "unsupported url" in msg:
            raise ValueError(f"Invalid or unsupported URL: {url}") from exc
        raise ValueError(f"Failed to retrieve video info: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Unexpected error while retrieving video info: {exc}") from exc

    if info is None:
        raise ValueError(f"Could not extract info for URL: {url}")

    title: str = info.get("title", "Untitled")
    duration: float = float(info.get("duration") or 0)

    # Pick the best thumbnail
    thumbnails = info.get("thumbnails") or []
    thumbnail_url = ""
    if thumbnails:
        # Prefer the last (usually highest quality) thumbnail
        thumbnail_url = thumbnails[-1].get("url", "")
    if not thumbnail_url:
        thumbnail_url = info.get("thumbnail", "")

    # Collect video-only formats that have resolution info
    formats: list[VideoFormat] = []
    seen_resolutions: set[str] = set()

    raw_formats = info.get("formats") or []
    for fmt in raw_formats:
        height = fmt.get("height")
        if height is None:
            continue
        # Skip audio-only streams
        vcodec = fmt.get("vcodec", "none")
        if vcodec == "none":
            continue

        resolution = f"{fmt.get('width', '?')}x{height}"
        format_id = fmt.get("format_id", "")
        ext = fmt.get("ext", "mp4")
        filesize = fmt.get("filesize") or fmt.get("filesize_approx")

        # Deduplicate by resolution – keep the first (usually best) for each
        res_key = f"{height}p-{ext}"
        if res_key in seen_resolutions:
            continue
        seen_resolutions.add(res_key)

        formats.append(
            VideoFormat(
                format_id=format_id,
                resolution=resolution,
                ext=ext,
                filesize_approx=int(filesize) if filesize else None,
            )
        )

    # Sort formats by height descending
    formats.sort(
        key=lambda f: int(f.resolution.split("x")[-1]) if "x" in f.resolution else 0,
        reverse=True,
    )

    logger.info("Retrieved info for '%s' – %.1fs, %d formats", title, duration, len(formats))

    return VideoInfo(
        title=title,
        duration=duration,
        thumbnail_url=thumbnail_url,
        formats=formats,
    )
