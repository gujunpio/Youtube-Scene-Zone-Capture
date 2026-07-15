"""Data models for the YouTube Scene Capture Tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CaptureMode(str, Enum):
    """Whether to capture the full frame or a cropped region."""
    FULL_FRAME = "full"
    CROPPED = "crop"


class OutputFormat(str, Enum):
    """Image output format for captured frames."""
    PNG = "png"
    JPG = "jpg"


@dataclass
class CropRect:
    """Rectangle defining a crop region within a video frame."""
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("CropRect width and height must be positive")
        if self.x < 0 or self.y < 0:
            raise ValueError("CropRect x and y must be non-negative")


@dataclass
class VideoFormat:
    """A single available format/quality option for a video."""
    format_id: str
    resolution: str
    ext: str
    filesize_approx: Optional[int] = None


@dataclass
class VideoInfo:
    """Metadata about a video retrieved from its URL."""
    title: str
    duration: float  # seconds
    thumbnail_url: str
    formats: list[VideoFormat] = field(default_factory=list)


@dataclass
class CaptureConfig:
    """Full configuration for a scene-capture job."""
    video_url: str
    video_path: str
    interval_seconds: float
    capture_mode: CaptureMode
    crop_rect: Optional[CropRect]
    output_dir: str
    output_format: OutputFormat
    zip_after_done: bool = True
    keep_source_video: bool = False
