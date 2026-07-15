"""FastAPI application for YouTube Scene Capture Tool.

Single-user desktop app exposing an SSE-based API for downloading YouTube
videos, previewing frames, extracting scenes at intervals, and packaging
the results into a downloadable ZIP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from models.capture_config import CropRect, OutputFormat
from services import (
    output_packager,
    preview_service,
    scene_extraction_service,
    video_download_service,
    video_info_service,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="YouTube Scene Capture")

TEMP_DIR = Path(tempfile.gettempdir()) / "yt_scene_capture"
TEMP_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


class AppState:
    """Mutable, global state for the single-user app."""
    cancel_flag: bool = False
    # Track the current video_id so we can resume between steps
    current_video_id: Optional[str] = None
    current_video_duration: float = 0.0


state = AppState()

# Mount static files *after* all API routes are defined (see bottom), but
# we need the directory to exist now.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}


def _find_video_in(directory: Path) -> Optional[Path]:
    """Return the first video file in *directory*, or ``None``."""
    if not directory.is_dir():
        return None
    for entry in directory.iterdir():
        if entry.suffix.lower() in _VIDEO_EXTENSIONS and entry.is_file():
            return entry
    return None


def _sse(data: dict[str, Any]) -> str:
    """Format a dict as a Server-Sent Event ``data:`` line."""
    return f"data: {json.dumps(data)}\n\n"


def _dir_size(path: Path) -> int:
    """Return total size of all files under *path* in bytes."""
    total = 0
    if path.is_dir():
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    return total


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _cleanup_old_sessions(exclude_id: Optional[str] = None) -> int:
    """Delete all session directories except *exclude_id*. Returns freed bytes."""
    freed = 0
    if not TEMP_DIR.is_dir():
        return freed
    for entry in TEMP_DIR.iterdir():
        if entry.is_dir() and entry.name != exclude_id:
            size = _dir_size(entry)
            try:
                import shutil
                shutil.rmtree(entry, ignore_errors=True)
                freed += size
                logger.info("Cleaned up session %s (freed %s)", entry.name, _format_size(size))
            except Exception as exc:
                logger.warning("Failed to clean %s: %s", entry.name, exc)
    return freed


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health-check endpoint used by Docker HEALTHCHECK."""
    import shutil
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    return JSONResponse({"status": "ok", "ffmpeg_available": ffmpeg_ok})


@app.get("/")
async def index():
    """Serve the frontend SPA."""
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return JSONResponse({"message": "Static frontend not found. Place index.html in /static."})


# ---- Video info ----------------------------------------------------------

@app.post("/api/info")
async def api_info(request: Request):
    """Return video metadata for a given URL."""
    body = await request.json()
    url: str = body.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "url is required", "message": "url is required"}, status_code=400)

    try:
        info = await asyncio.to_thread(video_info_service.get_info, url)
    except ValueError as exc:
        return JSONResponse({"error": str(exc), "message": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("Unexpected error in /api/info")
        return JSONResponse({"error": f"Server error: {exc}", "message": f"Server error: {exc}"}, status_code=500)

    return JSONResponse({
        "title": info.title,
        "duration": info.duration,
        "thumbnail_url": info.thumbnail_url,
        "formats": [asdict(f) for f in info.formats],
    })


# ---- Download ------------------------------------------------------------

@app.post("/api/download")
async def api_download(request: Request):
    """Download a video and stream progress via SSE."""
    body = await request.json()
    url: str = body.get("url", "").strip()
    format_id: str = body.get("format_id", "best720")

    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)

    video_id = uuid.uuid4().hex[:8]
    work_dir = TEMP_DIR / video_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Let's keep existing sessions for history list. Only delete on manual cleanup.

    state.cancel_flag = False
    state.current_video_id = video_id

    async def _generate() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def progress_cb(percent: float, speed: str, eta: str) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"status": "downloading", "percent": percent, "speed": speed, "eta": eta},
            )

        def cancel_ck() -> bool:
            return state.cancel_flag

        def _run_download() -> str:
            return video_download_service.download(
                url=url,
                format_id=format_id,
                output_dir=str(work_dir),
                progress_callback=progress_cb,
                cancel_check=cancel_ck,
            )

        # Start the download in a thread
        download_task = asyncio.ensure_future(asyncio.to_thread(_run_download))

        def _on_done(fut: asyncio.Future) -> None:  # type: ignore[type-arg]
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        download_task.add_done_callback(_on_done)

        # Stream progress events until the download finishes
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse(item)

        # Check result
        try:
            video_path = download_task.result()
            # Store duration for later extraction step
            try:
                info = await asyncio.to_thread(video_info_service.get_info, url)
                state.current_video_duration = info.duration
            except Exception:
                state.current_video_duration = 0.0

            # Save meta.json for history listing
            try:
                meta = {
                    "video_id": video_id,
                    "title": info.title if 'info' in locals() else "YouTube Video",
                    "url": url,
                    "duration": state.current_video_duration,
                    "thumbnail_url": info.thumbnail_url if 'info' in locals() else "",
                }
                with open(work_dir / "meta.json", "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            yield _sse({"status": "done", "video_id": video_id})
        except InterruptedError:
            yield _sse({"status": "cancelled", "message": "Download cancelled"})
        except Exception as exc:
            logger.exception("Download failed for %s", url)
            yield _sse({"status": "error", "message": str(exc)})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- Preview -------------------------------------------------------------

@app.get("/api/preview/{video_id}")
async def api_preview(video_id: str, t: float = Query(0)):
    """Extract and return a single preview frame at time *t*."""
    work_dir = TEMP_DIR / video_id
    video = _find_video_in(work_dir)
    if video is None:
        return JSONResponse({"error": "Video not found"}, status_code=404)

    try:
        preview_path = await asyncio.to_thread(
            preview_service.extract_frame, str(video), t,
        )
    except Exception as exc:
        logger.exception("Preview extraction failed")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return FileResponse(preview_path, media_type="image/jpeg")


# ---- Video dimensions ----------------------------------------------------

@app.get("/api/video-dims/{video_id}")
async def api_video_dims(video_id: str):
    """Return the width and height of the downloaded video."""
    work_dir = TEMP_DIR / video_id
    video = _find_video_in(work_dir)
    if video is None:
        return JSONResponse({"error": "Video not found"}, status_code=404)

    try:
        w, h = await asyncio.to_thread(
            preview_service.get_video_dimensions, str(video),
        )
    except Exception as exc:
        logger.exception("Could not read dimensions")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"width": w, "height": h})


# ---- Extract frames ------------------------------------------------------

@app.post("/api/extract")
async def api_extract(request: Request):
    """Extract frames at regular intervals and stream progress via SSE."""
    body = await request.json()
    video_id: str = body.get("video_id", "")
    interval: float = float(body.get("interval", 5))
    mode: str = body.get("mode", "full")  # "full" or "crop"
    crop_data: Optional[dict] = body.get("crop")
    fmt: str = body.get("format", "jpg")
    start_time: float = float(body.get("start_time", 0))
    end_time: float = float(body.get("end_time", 0))
    create_zip: bool = bool(body.get("create_zip", True))

    work_dir = TEMP_DIR / video_id
    video = _find_video_in(work_dir)
    if video is None:
        return JSONResponse({"error": "Video not found"}, status_code=404)

    frames_dir = work_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    crop_rect: Optional[CropRect] = None
    if mode == "crop" and crop_data:
        crop_rect = CropRect(
            x=int(crop_data["x"]),
            y=int(crop_data["y"]),
            width=int(crop_data["width"]),
            height=int(crop_data["height"]),
        )

    output_format = OutputFormat.PNG if fmt.lower() == "png" else OutputFormat.JPG

    # Determine duration
    duration = state.current_video_duration
    if duration <= 0:
        try:
            # Fallback: use ffprobe to get duration
            import subprocess, sys
            _cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(video),
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=_cf,
            )
            duration = float(result.stdout.decode().strip())
        except Exception:
            duration = 0.0

    state.cancel_flag = False

    # Calculate effective duration for frame estimation
    effective_end = end_time if end_time > 0 else duration
    effective_start = max(0, start_time)
    effective_duration = effective_end - effective_start
    if effective_duration <= 0:
        effective_duration = duration

    # Estimate total frames for current_frame reporting
    estimated_total = int(effective_duration / interval) + 1 if effective_duration > 0 else 0

    async def _generate() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def progress_cb(percent: float) -> None:
            current_frame = int(percent / 100 * estimated_total) if estimated_total > 0 else 0
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"status": "extracting", "percent": percent, "current_frame": current_frame},
            )

        def cancel_ck() -> bool:
            return state.cancel_flag

        def _run_extraction() -> list[str]:
            return scene_extraction_service.extract(
                video_path=str(video),
                interval_seconds=interval,
                crop_rect=crop_rect,
                output_dir=str(frames_dir),
                output_format=output_format,
                duration=duration,
                progress_callback=progress_cb,
                cancel_check=cancel_ck,
                start_time=start_time,
                end_time=end_time,
            )

        extract_task = asyncio.ensure_future(asyncio.to_thread(_run_extraction))

        def _on_done(fut: asyncio.Future) -> None:  # type: ignore[type-arg]
            loop.call_soon_threadsafe(queue.put_nowait, None)

        extract_task.add_done_callback(_on_done)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse(item)

        try:
            frames = extract_task.result()
            total_frames = len(frames)

            if create_zip:
                # Package into a ZIP
                yield _sse({"status": "packaging", "percent": 100})
                zip_path = str(work_dir / "result.zip")
                await asyncio.to_thread(output_packager.package, str(frames_dir), zip_path)

                yield _sse({
                    "status": "done",
                    "total_frames": total_frames,
                    "create_zip": True,
                    "download_url": f"/api/result/{video_id}",
                })
            else:
                # Direct download mode (send relative frame paths/filenames)
                filenames = [os.path.basename(f) for f in frames]
                yield _sse({
                    "status": "done",
                    "total_frames": total_frames,
                    "create_zip": False,
                    "video_id": video_id,
                    "frames": filenames,
                })
        except InterruptedError:
            yield _sse({"status": "cancelled", "message": "Extraction cancelled"})
        except Exception as exc:
            logger.exception("Extraction failed")
            yield _sse({"status": "error", "message": str(exc)})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- Download result -----------------------------------------------------

@app.get("/api/result/{video_id}")
async def api_result(video_id: str):
    """Serve the packaged ZIP of extracted frames."""
    zip_path = TEMP_DIR / video_id / "result.zip"
    if not zip_path.is_file():
        return JSONResponse({"error": "Result not found"}, status_code=404)

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"frames_{video_id}.zip",
    )


# ---- Serve single frame --------------------------------------------------

@app.get("/api/frame/{video_id}/{filename}")
async def api_frame(video_id: str, filename: str):
    """Serve a single extracted frame image."""
    frame_path = TEMP_DIR / video_id / "frames" / filename
    if not frame_path.is_file():
        return JSONResponse({"error": "Frame not found"}, status_code=404)
    ext = frame_path.suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    return FileResponse(path=str(frame_path), media_type=media_type)


# ---- Cancel --------------------------------------------------------------

@app.post("/api/cancel")
async def api_cancel():
    """Set the global cancel flag so running operations abort."""
    state.cancel_flag = True
    logger.info("Cancel requested")
    return JSONResponse({"status": "cancelled"})


# ---- Storage info --------------------------------------------------------

@app.get("/api/storage")
async def api_storage():
    """Return storage usage of the temp directory."""
    total_size = await asyncio.to_thread(_dir_size, TEMP_DIR)
    sessions = []
    if TEMP_DIR.is_dir():
        for entry in TEMP_DIR.iterdir():
            if entry.is_dir():
                size = _dir_size(entry)
                # Try to load meta.json
                meta = {}
                meta_path = entry / "meta.json"
                if meta_path.is_file():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                    except Exception:
                        pass
                
                # Verify video file exists inside session folder
                video_exists = _find_video_in(entry) is not None
                
                # Only include in history if metadata or video is present
                if video_exists:
                    sessions.append({
                        "id": entry.name,
                        "size": size,
                        "size_human": _format_size(size),
                        "title": meta.get("title", f"Session {entry.name}"),
                        "url": meta.get("url", ""),
                        "duration": meta.get("duration", 0.0),
                        "thumbnail_url": meta.get("thumbnail_url", ""),
                    })
    return JSONResponse({
        "total_size": total_size,
        "total_size_human": _format_size(total_size),
        "sessions": sessions,
        "temp_dir": str(TEMP_DIR),
    })


# ---- Select history ------------------------------------------------------

@app.post("/api/select/{video_id}")
async def api_select(video_id: str):
    """Select a downloaded video from history."""
    work_dir = TEMP_DIR / video_id
    video = _find_video_in(work_dir)
    if video is None:
        return JSONResponse({"error": "Video not found", "message": "Video not found"}, status_code=404)

    meta = {}
    meta_path = work_dir / "meta.json"
    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass

    state.current_video_id = video_id
    state.current_video_duration = meta.get("duration", 0.0)

    try:
        w, h = await asyncio.to_thread(preview_service.get_video_dimensions, str(video))
    except Exception:
        w, h = 0, 0

    return JSONResponse({
        "status": "ok",
        "video_id": video_id,
        "title": meta.get("title", f"Session {video_id}"),
        "duration": state.current_video_duration,
        "thumbnail_url": meta.get("thumbnail_url", ""),
        "width": w,
        "height": h,
    })


# ---- Cleanup -------------------------------------------------------------

@app.post("/api/cleanup")
async def api_cleanup():
    """Delete all temp data (videos, frames, zips)."""
    freed = await asyncio.to_thread(_cleanup_old_sessions, None)
    state.current_video_id = None
    state.current_video_duration = 0.0
    logger.info("Manual cleanup freed %s", _format_size(freed))
    return JSONResponse({
        "status": "ok",
        "freed": freed,
        "freed_human": _format_size(freed),
    })


# ---------------------------------------------------------------------------
# Static file mount (must be last so it doesn't shadow API routes)
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
