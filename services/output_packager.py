"""Service for packaging extracted frames into a ZIP and cleaning up."""

from __future__ import annotations

import logging
import os
import re
import zipfile

logger = logging.getLogger(__name__)

# Image extensions we care about
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def package(frames_dir: str, zip_output_path: str) -> str:
    """Create a ZIP archive of all image files in *frames_dir*.

    Images are sorted numerically by filename (e.g. ``1.jpg``, ``2.jpg``, …).

    Args:
        frames_dir: Directory containing the extracted frame images.
        zip_output_path: Full path for the resulting ``.zip`` file.

    Returns:
        Absolute path to the created ZIP file.
    """
    images = _sorted_images(frames_dir)
    if not images:
        logger.warning("No images found in %s – creating empty zip", frames_dir)

    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img_path in images:
            arcname = os.path.basename(img_path)
            zf.write(img_path, arcname)

    logger.info("Packaged %d images → %s", len(images), zip_output_path)
    return os.path.abspath(zip_output_path)


def cleanup_video(video_path: str) -> None:
    """Delete the source video file if it exists.

    Silently ignores missing files.
    """
    try:
        if os.path.isfile(video_path):
            os.remove(video_path)
            logger.info("Deleted source video: %s", video_path)
    except OSError as exc:
        logger.warning("Could not delete video %s: %s", video_path, exc)


def _sorted_images(directory: str) -> list[str]:
    """Collect image files from *directory* and sort them numerically."""
    items: list[tuple[int, str]] = []
    for entry in os.listdir(directory):
        _, ext = os.path.splitext(entry)
        if ext.lower() not in _IMAGE_EXTENSIONS:
            continue
        full_path = os.path.join(directory, entry)
        # Try to extract numeric stem for sorting
        match = re.match(r"(\d+)", os.path.splitext(entry)[0])
        sort_key = int(match.group(1)) if match else 0
        items.append((sort_key, full_path))
    items.sort(key=lambda t: t[0])
    return [path for _, path in items]
