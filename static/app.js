/* ========================================
   YouTube Scene Capture — App Logic
   ======================================== */

// --- State ---
const state = {
    videoId: null,
    videoUrl: null,
    videoDimensions: { width: 0, height: 0 },
    videoDuration: 0,
    cropRect: { x: 0, y: 0, width: 0, height: 0 },
    interval: 5,
    startTime: 0,
    endTime: 0,
    captureMode: 'full',
    outputFormat: 'png',
    isDownloading: false,
    isExtracting: false,
    lastResult: null
};

// --- DOM References ---
const dom = {
    urlInput: document.getElementById('url-input'),
    btnFetch: document.getElementById('btn-fetch'),
    videoInfo: document.getElementById('video-info'),
    videoThumbnail: document.getElementById('video-thumbnail'),
    videoTitle: document.getElementById('video-title'),
    videoDuration: document.getElementById('video-duration'),
    qualitySelect: document.getElementById('quality-select'),
    btnDownload: document.getElementById('btn-download'),
    downloadProgressArea: document.getElementById('download-progress-area'),
    downloadProgressBar: document.getElementById('download-progress-bar'),
    downloadPercent: document.getElementById('download-percent'),
    downloadDetails: document.getElementById('download-details'),

    sectionSettings: document.getElementById('section-settings'),
    intervalPills: document.getElementById('interval-pills'),
    customIntervalWrap: document.getElementById('custom-interval-wrap'),
    customInterval: document.getElementById('custom-interval'),
    startH: document.getElementById('start-h'),
    startM: document.getElementById('start-m'),
    startS: document.getElementById('start-s'),
    endH: document.getElementById('end-h'),
    endM: document.getElementById('end-m'),
    endS: document.getElementById('end-s'),
    rangeTrack: document.getElementById('range-track'),
    rangeProgress: document.getElementById('range-progress'),
    thumbStart: document.getElementById('thumb-start'),
    thumbEnd: document.getElementById('thumb-end'),
    frameCount: document.getElementById('frame-count'),
    cropRegion: document.getElementById('crop-region'),
    previewCanvas: document.getElementById('preview-canvas'),
    canvasHint: document.getElementById('canvas-hint'),
    cropX: document.getElementById('crop-x'),
    cropY: document.getElementById('crop-y'),
    cropW: document.getElementById('crop-w'),
    cropH: document.getElementById('crop-h'),

    sectionOutput: document.getElementById('section-output'),
    zipCheck: document.getElementById('zip-check'),
    btnExtract: document.getElementById('btn-extract'),
    extractProgressArea: document.getElementById('extract-progress-area'),
    extractProgressBar: document.getElementById('extract-progress-bar'),
    extractPercent: document.getElementById('extract-percent'),
    extractDetails: document.getElementById('extract-details'),
    btnCancel: document.getElementById('btn-cancel'),
    resultArea: document.getElementById('result-area'),
    resultText: document.getElementById('result-text'),
    btnResult: document.getElementById('btn-result'),

    toastContainer: document.getElementById('toast-container'),
    storageSize: document.getElementById('storage-size'),
    storagePath: document.getElementById('storage-path'),
    btnCleanup: document.getElementById('btn-cleanup'),
    historySection: document.getElementById('history-section'),
    historySelect: document.getElementById('history-select')
};

// --- Helpers ---
function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return h > 0
        ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
        : `${m}:${String(s).padStart(2, '0')}`;
}

function formatSize(bytes) {
    if (!bytes) return 'Unknown size';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return `${size.toFixed(1)} ${units[i]}`;
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    dom.toastContainer.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('toast-out');
        toast.addEventListener('animationend', () => toast.remove());
    }, 4000);
}

function setButtonLoading(btn, loading) {
    const text = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.btn-loader');
    if (text) text.hidden = loading;
    if (loader) loader.hidden = !loading;
    btn.disabled = loading;
}

function revealSection(el) {
    el.hidden = false;
    el.classList.remove('section-reveal');
    // Trigger reflow to restart animation
    void el.offsetWidth;
    el.classList.add('section-reveal');
}

// --- SSE Stream Reader ---
async function streamRequest(url, body, onData) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({ message: 'Request failed' }));
        throw new Error(err.message || `HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.slice(6));
                    onData(data);
                } catch (e) { /* skip malformed JSON */ }
            }
        }
    }

    // Process any remaining data in buffer
    if (buffer.startsWith('data: ')) {
        try {
            const data = JSON.parse(buffer.slice(6));
            onData(data);
        } catch (e) { /* skip */ }
    }
}

// =========================================
// Section 1: Video Input
// =========================================

dom.btnFetch.addEventListener('click', fetchVideoInfo);
dom.urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') fetchVideoInfo();
});

async function fetchVideoInfo() {
    const url = dom.urlInput.value.trim();
    if (!url) {
        showToast('Please paste a YouTube URL', 'error');
        dom.urlInput.focus();
        return;
    }

    setButtonLoading(dom.btnFetch, true);
    dom.videoInfo.hidden = true;

    try {
        const res = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.message || 'Failed to fetch video info');
        }

        const info = await res.json();
        state.videoUrl = url;

        // Populate UI
        dom.videoThumbnail.src = info.thumbnail_url;
        dom.videoTitle.textContent = info.title;
        dom.videoDuration.textContent = formatDuration(info.duration);

        // Populate format dropdown
        dom.qualitySelect.innerHTML = '';
        const formats = info.formats || [];

        // Sort: prefer higher resolution
        formats.sort((a, b) => {
            const resA = parseInt(a.resolution) || 0;
            const resB = parseInt(b.resolution) || 0;
            return resB - resA;
        });

        let defaultSelected = false;
        formats.forEach((fmt) => {
            const opt = document.createElement('option');
            opt.value = fmt.format_id;
            const sizeStr = fmt.filesize_approx ? ` — ${formatSize(fmt.filesize_approx)}` : '';
            opt.textContent = `${fmt.resolution} (${fmt.ext})${sizeStr}`;
            if (!defaultSelected && fmt.resolution && fmt.resolution.includes('720')) {
                opt.selected = true;
                defaultSelected = true;
            }
            dom.qualitySelect.appendChild(opt);
        });

        // If no 720p found, select first
        if (!defaultSelected && dom.qualitySelect.options.length > 0) {
            dom.qualitySelect.options[0].selected = true;
        }

        // Store duration and initialize time range
        state.videoDuration = info.duration;
        state.startTime = 0;
        state.endTime = info.duration;

        secondsToHmsInputs(0, dom.startH, dom.startM, dom.startS);
        secondsToHmsInputs(info.duration, dom.endH, dom.endM, dom.endS);

        updateSliderFromTimes();
        updateFrameEstimate();

        dom.videoInfo.hidden = false;
        showToast('Video info loaded!', 'success');

    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        setButtonLoading(dom.btnFetch, false);
    }
}

// --- Download Video ---
dom.btnDownload.addEventListener('click', downloadVideo);

async function downloadVideo() {
    const formatId = dom.qualitySelect.value;
    if (!formatId) {
        showToast('Please select a quality', 'error');
        return;
    }

    if (state.isDownloading) return;
    state.isDownloading = true;

    setButtonLoading(dom.btnDownload, true);
    dom.downloadProgressArea.hidden = false;
    dom.downloadProgressBar.style.width = '0%';
    dom.downloadPercent.textContent = '0%';
    dom.downloadDetails.textContent = 'Starting download...';

    // Hide sections 2 & 3 during new download
    dom.sectionSettings.hidden = true;
    dom.sectionOutput.hidden = true;

    try {
        await streamRequest('/api/download', {
            url: state.videoUrl,
            format_id: formatId
        }, (data) => {
            if (data.status === 'downloading') {
                const pct = data.percent || 0;
                dom.downloadProgressBar.style.width = `${pct}%`;
                dom.downloadPercent.textContent = `${pct.toFixed(1)}%`;
                const parts = [];
                if (data.speed) parts.push(`Speed: ${data.speed}`);
                if (data.eta) parts.push(`ETA: ${data.eta}`);
                dom.downloadDetails.textContent = parts.join('  ·  ');
            } else if (data.status === 'done') {
                state.videoId = data.video_id;
                dom.downloadProgressBar.style.width = '100%';
                dom.downloadPercent.textContent = '100%';
                dom.downloadDetails.textContent = 'Download complete!';
                showToast('Video downloaded successfully!', 'success');
                onVideoDownloaded();
            } else if (data.status === 'error') {
                throw new Error(data.message || 'Download failed');
            }
        });

    } catch (err) {
        showToast(err.message, 'error');
        dom.downloadDetails.textContent = 'Download failed';
    } finally {
        state.isDownloading = false;
        setButtonLoading(dom.btnDownload, false);
    }
}

async function onVideoDownloaded() {
    // Fetch video dimensions
    try {
        const res = await fetch(`/api/video-dims/${state.videoId}`);
        if (res.ok) {
            const dims = await res.json();
            state.videoDimensions.width = dims.width;
            state.videoDimensions.height = dims.height;
        }
    } catch (e) {
        console.warn('Could not fetch video dimensions:', e);
    }

    // Show settings & output sections
    revealSection(dom.sectionSettings);
    revealSection(dom.sectionOutput);

    // Reset extraction UI
    dom.extractProgressArea.hidden = true;
    dom.resultArea.hidden = true;

    // Load preview for crop
    loadPreviewImage();

    // Update storage size display
    updateStorageInfo();
}

// =========================================
// Section 2: Capture Settings
// =========================================

// --- Interval Pills ---
dom.intervalPills.addEventListener('click', (e) => {
    const pill = e.target.closest('.pill');
    if (!pill) return;

    // Update active state
    dom.intervalPills.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');

    const val = pill.dataset.value;
    if (val === 'custom') {
        dom.customIntervalWrap.hidden = false;
        state.interval = parseFloat(dom.customInterval.value) || 5;
    } else {
        dom.customIntervalWrap.hidden = true;
        state.interval = parseFloat(val);
    }
    updateFrameEstimate();
});

dom.customInterval.addEventListener('input', () => {
    const val = parseFloat(dom.customInterval.value);
    if (val && val > 0) {
        state.interval = val;
        updateFrameEstimate();
    }
});

// --- HMS Conversion Helpers ---
function secondsToHms(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return { h, m, s };
}

function hmsToSeconds(h, m, s) {
    return (parseInt(h) || 0) * 3600 + (parseInt(m) || 0) * 60 + (parseInt(s) || 0);
}

function secondsToHmsInputs(seconds, inputH, inputM, inputS) {
    const { h, m, s } = secondsToHms(seconds);
    inputH.value = h;
    inputM.value = String(m).padStart(2, '0');
    inputS.value = String(s).padStart(2, '0');
}

// --- Sync Slider Position from state.startTime & state.endTime ---
function updateSliderFromTimes() {
    if (!state.videoDuration) return;
    const startPct = (state.startTime / state.videoDuration) * 100;
    const endPct = (state.endTime / state.videoDuration) * 100;

    dom.thumbStart.style.left = `${startPct}%`;
    dom.thumbEnd.style.left = `${endPct}%`;
    dom.rangeProgress.style.left = `${startPct}%`;
    dom.rangeProgress.style.width = `${endPct - startPct}%`;
}

// --- Sync HMS Inputs from state.startTime & state.endTime ---
function updateHmsInputsFromTimes() {
    secondsToHmsInputs(state.startTime, dom.startH, dom.startM, dom.startS);
    secondsToHmsInputs(state.endTime, dom.endH, dom.endM, dom.endS);
}

// --- Read HMS Inputs and update state ---
function readHmsInputs() {
    const startVal = hmsToSeconds(dom.startH.value, dom.startM.value, dom.startS.value);
    const endVal = hmsToSeconds(dom.endH.value, dom.endM.value, dom.endS.value);

    // Validate and clamp
    state.startTime = Math.max(0, Math.min(startVal, state.videoDuration));
    state.endTime = Math.max(0, Math.min(endVal, state.videoDuration));

    // Ensure start < end
    if (state.startTime >= state.endTime) {
        state.endTime = Math.min(state.startTime + 1, state.videoDuration);
        secondsToHmsInputs(state.endTime, dom.endH, dom.endM, dom.endS);
    }

    updateSliderFromTimes();
    updateFrameEstimate();
}

// --- Dual Range Slider Dragging Logic ---
let activeThumb = null;

function handleSliderDrag(e) {
    if (!activeThumb || !state.videoDuration) return;
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const rect = dom.rangeTrack.getBoundingClientRect();
    let pct = (clientX - rect.left) / rect.width;
    pct = Math.max(0, Math.min(1, pct));
    const seconds = pct * state.videoDuration;

    if (activeThumb === dom.thumbStart) {
        state.startTime = Math.min(seconds, state.endTime - 1);
        if (state.startTime < 0) state.startTime = 0;
    } else if (activeThumb === dom.thumbEnd) {
        state.endTime = Math.max(seconds, state.startTime + 1);
        if (state.endTime > state.videoDuration) state.endTime = state.videoDuration;
    }

    updateSliderFromTimes();
    updateHmsInputsFromTimes();
    updateFrameEstimate();
}

function startThumbDrag(thumb, e) {
    e.preventDefault();
    activeThumb = thumb;
    document.addEventListener('mousemove', handleSliderDrag);
    document.addEventListener('mouseup', stopThumbDrag);
    document.addEventListener('touchmove', handleSliderDrag, { passive: false });
    document.addEventListener('touchend', stopThumbDrag);
}

function stopThumbDrag() {
    activeThumb = null;
    document.removeEventListener('mousemove', handleSliderDrag);
    document.removeEventListener('mouseup', stopThumbDrag);
    document.removeEventListener('touchmove', handleSliderDrag);
    document.removeEventListener('touchend', stopThumbDrag);
}

dom.thumbStart.addEventListener('mousedown', (e) => startThumbDrag(dom.thumbStart, e));
dom.thumbStart.addEventListener('touchstart', (e) => startThumbDrag(dom.thumbStart, e));
dom.thumbEnd.addEventListener('mousedown', (e) => startThumbDrag(dom.thumbEnd, e));
dom.thumbEnd.addEventListener('touchstart', (e) => startThumbDrag(dom.thumbEnd, e));

// Allow clicking on track to seek nearest handle
dom.rangeTrack.addEventListener('mousedown', (e) => {
    if (e.target === dom.thumbStart || e.target === dom.thumbEnd || !state.videoDuration) return;
    const rect = dom.rangeTrack.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const seconds = pct * state.videoDuration;

    let thumbToDrag = null;
    // Determine nearest handle
    if (Math.abs(seconds - state.startTime) < Math.abs(seconds - state.endTime)) {
        state.startTime = Math.min(seconds, state.endTime - 1);
        if (state.startTime < 0) state.startTime = 0;
        thumbToDrag = dom.thumbStart;
    } else {
        state.endTime = Math.max(seconds, state.startTime + 1);
        if (state.endTime > state.videoDuration) state.endTime = state.videoDuration;
        thumbToDrag = dom.thumbEnd;
    }
    
    updateSliderFromTimes();
    updateHmsInputsFromTimes();
    updateFrameEstimate();

    // Directly start drag session
    startThumbDrag(thumbToDrag, e);
});

// Event listeners for HH:MM:SS text boxes
[dom.startH, dom.startM, dom.startS, dom.endH, dom.endM, dom.endS].forEach(input => {
    input.addEventListener('change', readHmsInputs);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            readHmsInputs();
            input.blur();
        }
    });
});

// --- Frame Estimation ---
function updateFrameEstimate() {
    const effectiveDuration = (state.endTime || state.videoDuration) - state.startTime;
    if (effectiveDuration <= 0 || state.interval <= 0) {
        dom.frameCount.textContent = '~0';
        return;
    }
    const frames = Math.floor(effectiveDuration / state.interval) + 1;
    dom.frameCount.textContent = `~${frames}`;
}

// --- Mode Cards ---
document.querySelectorAll('.mode-card').forEach(card => {
    card.addEventListener('click', () => {
        document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        state.captureMode = card.dataset.mode;

        if (state.captureMode === 'crop') {
            dom.cropRegion.hidden = false;
            loadPreviewImage();
        } else {
            dom.cropRegion.hidden = true;
        }
    });
});

// --- Output Format Toggle ---
const toggleGroup = document.querySelector('.toggle-group');
document.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.outputFormat = btn.dataset.format;
        toggleGroup.dataset.active = btn.dataset.format;
    });
});
// Initialize toggle state
toggleGroup.dataset.active = 'png';

// =========================================
// Canvas Crop Selector
// =========================================

let canvasImage = null;
let scaleFactor = 1;
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let canvasRect = { x: 0, y: 0, w: 0, h: 0 }; // in canvas coordinates

function loadPreviewImage() {
    if (!state.videoId) return;

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
        canvasImage = img;
        const canvas = dom.previewCanvas;
        const container = canvas.parentElement;
        const displayWidth = container.clientWidth;
        const displayHeight = (img.height / img.width) * displayWidth;

        canvas.width = displayWidth;
        canvas.height = displayHeight;
        canvas.style.height = displayHeight + 'px';

        // Calculate scale factor (video pixels per canvas pixel)
        if (state.videoDimensions.width > 0) {
            scaleFactor = state.videoDimensions.width / displayWidth;
        } else {
            scaleFactor = img.width / displayWidth;
        }

        drawCanvas();
    };
    img.src = `/api/preview/${state.videoId}?t=0&_=${Date.now()}`;
}

function drawCanvas() {
    const canvas = dom.previewCanvas;
    const ctx = canvas.getContext('2d');

    // Draw image
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(canvasImage, 0, 0, canvas.width, canvas.height);

    // Draw crop overlay if exists
    if (canvasRect.w > 0 && canvasRect.h > 0) {
        // Dim outside area
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Clear selected area (show original image)
        ctx.save();
        ctx.beginPath();
        ctx.rect(canvasRect.x, canvasRect.y, canvasRect.w, canvasRect.h);
        ctx.clip();
        ctx.drawImage(canvasImage, 0, 0, canvas.width, canvas.height);
        ctx.restore();

        // Draw selection border
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 3]);
        ctx.strokeRect(canvasRect.x, canvasRect.y, canvasRect.w, canvasRect.h);
        ctx.setLineDash([]);

        // Fill selection with semi-transparent overlay
        ctx.fillStyle = 'rgba(99, 102, 241, 0.12)';
        ctx.fillRect(canvasRect.x, canvasRect.y, canvasRect.w, canvasRect.h);

        // Draw corner handles
        const handleSize = 8;
        ctx.fillStyle = '#6366f1';
        const corners = [
            [canvasRect.x, canvasRect.y],
            [canvasRect.x + canvasRect.w, canvasRect.y],
            [canvasRect.x, canvasRect.y + canvasRect.h],
            [canvasRect.x + canvasRect.w, canvasRect.y + canvasRect.h]
        ];
        corners.forEach(([cx, cy]) => {
            ctx.fillRect(cx - handleSize / 2, cy - handleSize / 2, handleSize, handleSize);
        });

        // Draw dimension label
        const videoW = Math.round(canvasRect.w * scaleFactor);
        const videoH = Math.round(canvasRect.h * scaleFactor);
        const label = `${videoW} × ${videoH}`;
        ctx.font = '600 13px Inter, sans-serif';
        const textMetrics = ctx.measureText(label);
        const labelX = canvasRect.x + canvasRect.w / 2;
        const labelY = canvasRect.y + canvasRect.h / 2;
        const padding = 6;
        const bgW = textMetrics.width + padding * 2;
        const bgH = 22;

        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.beginPath();
        ctx.roundRect(labelX - bgW / 2, labelY - bgH / 2, bgW, bgH, 4);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, labelX, labelY);
    }
}

function getCanvasCoords(e) {
    const rect = dom.previewCanvas.getBoundingClientRect();
    return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
}

dom.previewCanvas.addEventListener('mousedown', (e) => {
    if (!canvasImage) return;
    isDragging = true;
    dragStart = getCanvasCoords(e);
    dom.canvasHint.style.opacity = '0';
});

dom.previewCanvas.addEventListener('mousemove', (e) => {
    if (!isDragging || !canvasImage) return;
    const current = getCanvasCoords(e);

    canvasRect.x = Math.min(dragStart.x, current.x);
    canvasRect.y = Math.min(dragStart.y, current.y);
    canvasRect.w = Math.abs(current.x - dragStart.x);
    canvasRect.h = Math.abs(current.y - dragStart.y);

    // Clamp to canvas bounds
    canvasRect.x = Math.max(0, canvasRect.x);
    canvasRect.y = Math.max(0, canvasRect.y);
    if (canvasRect.x + canvasRect.w > dom.previewCanvas.width) {
        canvasRect.w = dom.previewCanvas.width - canvasRect.x;
    }
    if (canvasRect.y + canvasRect.h > dom.previewCanvas.height) {
        canvasRect.h = dom.previewCanvas.height - canvasRect.y;
    }

    updateCropInputsFromCanvas();
    requestAnimationFrame(drawCanvas);
});

document.addEventListener('mouseup', (e) => {
    if (isDragging) {
        isDragging = false;
        drawCanvas();
    }
});

function updateCropInputsFromCanvas() {
    state.cropRect.x = Math.round(canvasRect.x * scaleFactor);
    state.cropRect.y = Math.round(canvasRect.y * scaleFactor);
    state.cropRect.width = Math.round(canvasRect.w * scaleFactor);
    state.cropRect.height = Math.round(canvasRect.h * scaleFactor);

    dom.cropX.value = state.cropRect.x;
    dom.cropY.value = state.cropRect.y;
    dom.cropW.value = state.cropRect.width;
    dom.cropH.value = state.cropRect.height;
}

function updateCanvasFromCropInputs() {
    state.cropRect.x = parseInt(dom.cropX.value) || 0;
    state.cropRect.y = parseInt(dom.cropY.value) || 0;
    state.cropRect.width = parseInt(dom.cropW.value) || 0;
    state.cropRect.height = parseInt(dom.cropH.value) || 0;

    canvasRect.x = state.cropRect.x / scaleFactor;
    canvasRect.y = state.cropRect.y / scaleFactor;
    canvasRect.w = state.cropRect.width / scaleFactor;
    canvasRect.h = state.cropRect.height / scaleFactor;

    if (canvasImage) {
        requestAnimationFrame(drawCanvas);
    }
}

// Sync spinbox inputs → canvas
[dom.cropX, dom.cropY, dom.cropW, dom.cropH].forEach(input => {
    input.addEventListener('input', updateCanvasFromCropInputs);
});

// =========================================
// Section 3: Extraction
// =========================================

dom.btnExtract.addEventListener('click', startExtraction);
dom.btnCancel.addEventListener('click', cancelExtraction);
dom.btnResult.addEventListener('click', handleResultDownload);

async function handleResultDownload(e) {
    if (!state.lastResult || state.lastResult.create_zip) {
        // Normal ZIP download handled by browser
        return;
    }
    
    e.preventDefault();
    
    if ('showDirectoryPicker' in window) {
        try {
            // Prompt to select folder
            const dirHandle = await window.showDirectoryPicker({
                mode: 'readwrite'
            });
            
            showToast('Saving frames to selected folder...', 'info');
            setButtonLoading(dom.btnResult, true);
            
            const frames = state.lastResult.frames;
            const videoId = state.lastResult.video_id;
            let successCount = 0;
            
            for (let i = 0; i < frames.length; i++) {
                const filename = frames[i];
                const response = await fetch(`/api/frame/${videoId}/${filename}`);
                if (!response.ok) continue;
                
                const blob = await response.blob();
                const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
                const writable = await fileHandle.createWritable();
                await writable.write(blob);
                await writable.close();
                successCount++;
            }
            
            showToast(`Saved ${successCount} frames directly to folder!`, 'success');
        } catch (err) {
            if (err.name === 'AbortError') {
                showToast('Folder selection cancelled', 'warning');
            } else {
                console.error(err);
                showToast('Folder permission error. Falling back to default downloads.', 'warning');
                fallbackBulkDownload();
            }
        } finally {
            setButtonLoading(dom.btnResult, false);
        }
    } else {
        fallbackBulkDownload();
    }
}

function fallbackBulkDownload() {
    const frames = state.lastResult.frames;
    const videoId = state.lastResult.video_id;
    showToast(`Downloading ${frames.length} files. Allow multiple downloads if asked!`, 'info');
    
    frames.forEach((filename, idx) => {
        setTimeout(() => {
            const link = document.createElement('a');
            link.href = `/api/frame/${videoId}/${filename}`;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }, idx * 150);
    });
}

async function startExtraction() {
    if (!state.videoId) {
        showToast('No video downloaded yet', 'error');
        return;
    }
    if (state.isExtracting) return;

    // Validate crop region in crop mode
    if (state.captureMode === 'crop') {
        if (state.cropRect.width <= 0 || state.cropRect.height <= 0) {
            showToast('Please select a crop region on the canvas', 'error');
            return;
        }
    }

    state.isExtracting = true;
    setButtonLoading(dom.btnExtract, true);
    dom.extractProgressArea.hidden = false;
    dom.resultArea.hidden = true;
    dom.extractProgressBar.style.width = '0%';
    dom.extractPercent.textContent = '0%';
    dom.extractDetails.textContent = 'Starting extraction...';

    const payload = {
        video_id: state.videoId,
        interval: state.interval,
        mode: state.captureMode,
        crop: state.captureMode === 'crop' ? {
            x: state.cropRect.x,
            y: state.cropRect.y,
            width: state.cropRect.width,
            height: state.cropRect.height
        } : null,
        format: state.outputFormat,
        start_time: state.startTime,
        end_time: state.endTime,
        create_zip: dom.zipCheck.checked
    };

    try {
        await streamRequest('/api/extract', payload, (data) => {
            if (data.status === 'extracting') {
                const pct = data.percent || 0;
                dom.extractProgressBar.style.width = `${pct}%`;
                dom.extractPercent.textContent = `${pct.toFixed(1)}%`;
                dom.extractDetails.textContent = `Extracted ${data.current_frame || 0} frames...`;
            } else if (data.status === 'done') {
                dom.extractProgressBar.style.width = '100%';
                dom.extractPercent.textContent = '100%';
                dom.extractDetails.textContent = 'Extraction complete!';

                // Show result
                state.lastResult = data;
                dom.resultText.textContent = `Successfully extracted ${data.total_frames} frames!`;
                if (data.create_zip) {
                    dom.btnResult.href = data.download_url;
                    dom.btnResult.innerHTML = '📦 Download Results (ZIP)';
                } else {
                    dom.btnResult.href = '#';
                    dom.btnResult.innerHTML = '📁 Save Frames to Folder';
                }
                dom.resultArea.hidden = false;

                showToast(`Extracted ${data.total_frames} frames!`, 'success');
            } else if (data.status === 'error') {
                throw new Error(data.message || 'Extraction failed');
            }
        });
    } catch (err) {
        showToast(err.message, 'error');
        dom.extractDetails.textContent = 'Extraction failed';
    } finally {
        state.isExtracting = false;
        setButtonLoading(dom.btnExtract, false);
        updateStorageInfo();
    }
}

async function cancelExtraction() {
    try {
        const res = await fetch('/api/cancel', { method: 'POST' });
        if (res.ok) {
            showToast('Extraction cancelled', 'info');
            dom.extractDetails.textContent = 'Cancelled';
            dom.extractProgressArea.hidden = true;
            state.isExtracting = false;
            setButtonLoading(dom.btnExtract, false);
        }
    } catch (err) {
        showToast('Failed to cancel', 'error');
    }
}

// =========================================
// Window resize: redraw canvas
// =========================================
let resizeTimer;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (canvasImage && !dom.cropRegion.hidden) {
            // Recalculate on resize
            const canvas = dom.previewCanvas;
            const container = canvas.parentElement;
            const displayWidth = container.clientWidth;
            const displayHeight = (canvasImage.height / canvasImage.width) * displayWidth;
            const oldScaleFactor = scaleFactor;

            canvas.width = displayWidth;
            canvas.height = displayHeight;
            canvas.style.height = displayHeight + 'px';

            if (state.videoDimensions.width > 0) {
                scaleFactor = state.videoDimensions.width / displayWidth;
            } else {
                scaleFactor = canvasImage.width / displayWidth;
            }

            // Re-derive canvas rect from video coords
            canvasRect.x = state.cropRect.x / scaleFactor;
            canvasRect.y = state.cropRect.y / scaleFactor;
            canvasRect.w = state.cropRect.width / scaleFactor;
            canvasRect.h = state.cropRect.height / scaleFactor;

            drawCanvas();
        }
    }, 200);
});

// =========================================
// URL input Enter key & auto-paste detection
// =========================================
dom.urlInput.addEventListener('paste', () => {
    // Give the browser a moment to update the input value
    setTimeout(() => {
        const val = dom.urlInput.value.trim();
        if (val && (val.includes('youtube.com') || val.includes('youtu.be'))) {
            // Auto-fetch on paste if it looks like a YouTube URL
            fetchVideoInfo();
        }
    }, 100);
});

// =========================================
// Polyfill: CanvasRenderingContext2D.roundRect
// =========================================
if (!CanvasRenderingContext2D.prototype.roundRect) {
    CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, radii) {
        const r = typeof radii === 'number' ? radii : (radii?.[0] ?? 0);
        this.moveTo(x + r, y);
        this.arcTo(x + w, y, x + w, y + h, r);
        this.arcTo(x + w, y + h, x, y + h, r);
        this.arcTo(x, y + h, x, y, r);
        this.arcTo(x, y, x + w, y, r);
        this.closePath();
    };
}

// =========================================
// Storage Management
// =========================================
async function updateStorageInfo() {
    try {
        const res = await fetch('/api/storage');
        if (res.ok) {
            const data = await res.json();
            dom.storageSize.textContent = data.total_size_human;
            // Shorten the path display for readability if it's long
            let pathText = data.temp_dir;
            if (pathText.length > 30) {
                pathText = '...' + pathText.slice(-27);
            }
            dom.storagePath.textContent = `(${pathText})`;

            // Populate history list
            const sessions = data.sessions || [];
            if (sessions.length > 0) {
                dom.historySelect.innerHTML = '<option value="">-- Select from history --</option>';
                sessions.forEach(sess => {
                    const opt = document.createElement('option');
                    opt.value = sess.id;
                    opt.textContent = `${sess.title} (${sess.size_human})`;
                    if (state.videoId === sess.id) {
                        opt.selected = true;
                    }
                    dom.historySelect.appendChild(opt);
                });
                dom.historySection.hidden = false;
            } else {
                dom.historySection.hidden = true;
            }
        }
    } catch (e) {
        console.warn('Failed to update storage info:', e);
    }
}

async function selectVideoFromHistory() {
    const videoId = dom.historySelect.value;
    if (!videoId) return;

    dom.historySelect.disabled = true;
    try {
        const res = await fetch(`/api/select/${videoId}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            state.videoId = data.video_id;
            state.videoDuration = data.duration;

            secondsToHmsInputs(0, dom.startH, dom.startM, dom.startS);
            secondsToHmsInputs(data.duration, dom.endH, dom.endM, dom.endS);
            updateSliderFromTimes();
            updateFrameEstimate();

            onVideoDownloaded();
            showToast(`Loaded "${data.title}" from history`, 'success');
        } else {
            showToast('Failed to load video from history', 'error');
        }
    } catch (e) {
        showToast('Error loading video history', 'error');
    } finally {
        dom.historySelect.disabled = false;
    }
}

async function cleanupStorage() {
    if (confirm('Are you sure you want to delete all temporary downloads and extracted frames?')) {
        setButtonLoading(dom.btnCleanup, true);
        try {
            const res = await fetch('/api/cleanup', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                showToast(`Storage cleaned! Freed ${data.freed_human}`, 'success');
                // Hide active settings since files are deleted
                dom.sectionSettings.hidden = true;
                dom.sectionOutput.hidden = true;
                state.videoId = null;
                state.videoDuration = 0;
                dom.historySelect.innerHTML = '<option value="">-- Select from history --</option>';
                dom.historySection.hidden = true;
                updateStorageInfo();
            } else {
                showToast('Failed to clean storage', 'error');
            }
        } catch (err) {
            showToast('Error cleaning storage', 'error');
        } finally {
            setButtonLoading(dom.btnCleanup, false);
        }
    }
}

dom.btnCleanup.addEventListener('click', cleanupStorage);
dom.historySelect.addEventListener('change', selectVideoFromHistory);

// Initial storage update
updateStorageInfo();

