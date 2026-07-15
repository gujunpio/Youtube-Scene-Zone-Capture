# YouTube Scene Zone Capture

🎬 A premium, full-stack containerized Web UI tool to extract frames from any YouTube video at customizable intervals. Supports precise time range selection, canvas-based visual cropping, disk space auto-cleanup, and direct bulk image downloading into a folder without ZIP decompression.

---

## ✨ Features

- **Double-Ended Time Range Slider**: An interactive range slider with dual handles synced bidirectionally with HH:MM:SS text fields to precisely target sections of the video.
- **Estimated Frame Count**: Dynamic live calculation of how many frames will be extracted based on your target time range and capture interval.
- **Visual Crop Region Selector**: A canvas-based interactive cropper allowing you to draw a crop rectangle directly on a video preview frame. Fits coordinate scale ratios to raw video sizes automatically.
- **Bulk Folder Download (No ZIP)**: Utilizes the modern HTML5 **File System Access API** to let you download hundreds of frames directly into a folder on your computer with a single click, completely bypassing the need to unzip file archives.
- **Optional ZIP packaging**: Alternatively packages all extracted images into a single sorted ZIP archive.
- **SSE Real-time Progress Tracking**: Under the hood Server-Sent Events (SSE) stream the download progress (with speed & ETA) and extraction percentages to the UI.
- **Storage Management**: Display of disk usage with an auto-cleanup hook that purges old session files on new downloads, alongside a manual **🗑️ Cleanup** button.
- **Premium Dark Glassmorphism Theme**: An styled dark UI layout featuring fluid micro-animations, customizable responsive elements, and clean typography.
- **Dockerized Architecture**: Pre-bundled with Python 3.11, FFmpeg, and yt-dlp. Single command setup.

---

## 🛠️ Architecture

```
Youtube Capture Zone/
├── Dockerfile                    # Multi-stage image setup (Python 3.11 + FFmpeg)
├── docker-compose.yml            # Port mappings (8080) and named storage volumes
├── requirements.txt              # FastAPI, uvicorn, yt-dlp, Pillow
├── main.py                       # FastAPI application (Streaming responses + API routes)
├── models/
│   └── capture_config.py         # App dataclasses (CropRect, OutputFormat, etc.)
├── services/
│   ├── video_info_service.py     # yt-dlp metadata retriever
│   ├── video_download_service.py # yt-dlp downloader with progress piping
│   ├── preview_service.py        # Frame preview extraction via FFmpeg/ffprobe
│   ├── scene_extraction_service.py # Chunked frame extraction with crop filters
│   └── output_packager.py        # ZIP packaging & temporary files cleanup
└── static/
    ├── index.html                # App layout & styling structure
    ├── style.css                 # Custom premium CSS theme styles
    ├── app.js                    # Interactive canvas, slider logic & API caller
    └── favicon.png               # Custom branding favicon icon
```

---

## 🚀 Getting Started

### Prerequisites

Make sure you have [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/) installed on your machine.

### Installation & Deployment

1. Clone or copy this repository to your local workspace.
2. Open your terminal in the project directory.
3. Run the following command:
   ```bash
   docker-compose up --build -d
   ```
4. Once container is running and healthy, open your browser and navigate to:
   ```
   http://localhost:8080
   ```

### Local Development (Alternative)

If you wish to run the project without Docker, you will need **FFmpeg** and **ffprobe** installed and added to your system's PATH.

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the FastAPI server:
   ```bash
   python main.py
   ```
3. Open your browser at:
   ```
   http://localhost:8080
   ```

---

## 📖 How to Use

1. **Paste URL**: Insert any YouTube video URL into the video input box. Press **Enter** or click **Fetch Info**.
2. **Download Video**: Choose your preferred quality stream from the dropdown list and click **Download Video**.
3. **Set Time Range**: Drag the slider thumbs or type directly into the **HH:MM:SS** boxes to limit the scene extraction boundaries.
4. **Choose Interval & Mode**:
   - Choose a frame capture interval (e.g. every 2s, 5s, or custom seconds).
   - Choose either **Full Frame** or **Crop Region** mode. (If using Crop, click and drag your cursor over the preview canvas to target a specific region).
5. **Start Extraction**: Uncheck "Create ZIP archive" if you want to write files directly to a folder. Click **Start Extraction**.
6. **Download Results**:
   - **With ZIP**: Click **Download Results (ZIP)**.
   - **Without ZIP**: Click **Save Frames to Folder**, select your target local folder, authorize write access in your browser, and watch the frames get written directly to your disk!

---

## 💾 Storage Policy

All video downloads, zips, and temporary frame outputs are saved in the container's `/tmp/yt_scene_capture` folder, mapped to a Docker volume. 
- The backend automatically purges old cache directories when a new download session begins.
- You can manually purge all temp space by clicking **🗑️ Cleanup** in the page footer.
