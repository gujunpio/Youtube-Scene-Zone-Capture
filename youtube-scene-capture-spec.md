# Đặc tả triển khai: YouTube Scene Capture Tool

## 1. Tổng quan

**Mục tiêu**: Desktop app nhận link YouTube, tải video, trích ảnh scene theo khoảng thời gian cố định (2s/5s/10s/60s hoặc tuỳ chỉnh), hỗ trợ chụp toàn màn hình hoặc crop theo vùng cố định (chọn 1 lần, áp dụng cho toàn bộ ảnh), xuất ảnh đánh số thứ tự 1, 2, 3...n.

**Nguyên tắc thiết kế**: tải video về máy trước, xử lý offline bằng FFmpeg (không phụ thuộc mạng lúc trích ảnh, xử lý được video 1-2 tiếng trong vài phút).

**Stack đề xuất**:
- Backend logic: Python 3.11+
- Tải video: thư viện `yt-dlp` (import trực tiếp, không gọi CLI qua subprocess để dễ bắt lỗi và lấy progress callback)
- Xử lý ảnh: `ffmpeg` binary, gọi qua `subprocess`
- GUI: `PySide6` (Qt for Python)
- Đóng gói phân phối: `PyInstaller` → 1 file thực thi

---

## 2. Kiến trúc tổng thể

```
UI Layer (PySide6)
   │
   ├── VideoInfoService      → lấy metadata video (title, duration, thumbnail)
   ├── VideoDownloadService  → tải video, báo progress
   ├── PreviewService        → trích 1 frame để hiển thị cho việc chọn crop
   ├── CropSelector (widget)  → quản lý state vùng crop, đồng bộ kéo chuột <-> nhập tay
   ├── SceneExtractionService → gọi FFmpeg trích toàn bộ scene theo config
   └── OutputPackager        → đổi tên tuần tự, (tuỳ chọn) nén zip
```

Toàn bộ các Service là các class độc lập, không phụ thuộc trực tiếp vào UI, để dễ test và dễ thay UI sau này (VD chuyển sang web UI) mà không phải viết lại logic.

---

## 3. Luồng xử lý (end-to-end)

1. Người dùng nhập URL YouTube → bấm "Tải thông tin"
2. `VideoInfoService.get_info(url)` trả về: title, duration_seconds, thumbnail_url, available_formats
3. UI hiển thị thông tin, cho chọn chất lượng tải (khuyến nghị mặc định: 720p, đủ dùng cho việc chụp scene, giảm thời gian tải)
4. Người dùng bấm "Tải video" → `VideoDownloadService.download(url, format_id, on_progress)` tải file về thư mục tạm, báo % tiến độ qua callback
5. Sau khi tải xong, `PreviewService.extract_frame(video_path, timestamp=0)` trích 1 ảnh preview
6. UI hiển thị ảnh preview, người dùng:
   - Chọn chế độ: "Full màn hình" hoặc "Crop vùng cố định"
   - Nếu crop: kéo chuột vẽ khung HOẶC nhập tay 4 giá trị x, y, width, height (xem mục 5.3)
   - Chọn khoảng thời gian: dropdown (2/5/10/60s) hoặc nhập số giây tuỳ ý
7. Bấm "Bắt đầu trích ảnh" → `SceneExtractionService.extract(video_path, interval_seconds, crop_rect, output_dir, on_progress)`
8. `OutputPackager` đảm bảo file được đặt tên `1.png, 2.png, ..., n.png` theo đúng thứ tự thời gian, tuỳ chọn nén thành `.zip`
9. Xoá file video tạm (tuỳ chọn, có checkbox "Giữ lại video gốc")

---

## 4. Cấu trúc dữ liệu / Config schema

Đây là "hợp đồng dữ liệu" giữa UI và các Service, coding agent nên định nghĩa thành 1 dataclass/model dùng xuyên suốt:

```
CaptureConfig:
  video_url: str
  video_path: str            # đường dẫn video đã tải, điền sau bước download
  interval_seconds: float    # 2, 5, 10, 60, hoặc số tuỳ chỉnh
  capture_mode: enum { FULL_FRAME, CROPPED }
  crop_rect: {               # chỉ có giá trị khi capture_mode = CROPPED
    x: int
    y: int
    width: int
    height: int
  } | null
  output_dir: str
  output_format: enum { png, jpg }   # mặc định png (không nén, giữ chất lượng)
  zip_after_done: bool
  keep_source_video: bool
```

`crop_rect` luôn tính theo **toạ độ pixel gốc của video** (không phải toạ độ hiển thị trên UI), để đảm bảo FFmpeg crop đúng vị trí bất kể kích thước preview trên màn hình là bao nhiêu.

---

## 5. Chi tiết từng module

### 5.1 VideoInfoService
- **Input**: url (str)
- **Output**: object gồm title, duration_seconds, thumbnail_url, danh sách format khả dụng (resolution, filesize ước tính)
- **Trách nhiệm**: chỉ query metadata, KHÔNG tải file. Dùng để hiển thị cho người dùng xác nhận trước khi tải.

### 5.2 VideoDownloadService
- **Input**: url, format_id (hoặc mặc định "best video có sẵn ≤720p"), on_progress callback
- **Output**: đường dẫn file video đã tải về thư mục tạm
- **Trách nhiệm**: tải video, gọi callback với % tiến độ + tốc độ tải để UI cập nhật progress bar
- **Lưu ý**: nên giới hạn chất lượng tải mặc định (720p đủ cho screenshot thông thường) để giảm thời gian tải với video 1-2 tiếng; cho phép người dùng chọn chất lượng cao hơn nếu cần chi tiết ảnh sắc nét hơn.

### 5.3 PreviewService + CropSelector (phần "cả hai option")
- **PreviewService.extract_frame(video_path, timestamp)**: trích 1 frame làm ảnh preview để hiển thị, trả về path ảnh + kích thước gốc (width, height) của video
- **CropSelector**: widget quản lý 1 state duy nhất `crop_rect` với 2 nguồn input đổ vào cùng 1 hàm cập nhật:
  - **Nguồn 1 — kéo chuột**: người dùng kéo trên ảnh preview (đã bị scale xuống để vừa màn hình). Cần tính `scale_factor = video_width / preview_display_width` để quy đổi toạ độ kéo chuột về toạ độ gốc trước khi lưu vào `crop_rect`.
  - **Nguồn 2 — nhập tay**: 4 ô số (x, y, width, height) nhập trực tiếp theo toạ độ gốc.
  - Cả 2 nguồn phải gọi chung 1 hàm `update_crop_rect(x, y, w, h)` — hàm này vừa cập nhật state, vừa vẽ lại khung chọn trên ảnh preview (nhân với scale_factor theo chiều ngược lại), để đảm bảo 2 cách nhập luôn đồng bộ, không lệch dữ liệu.
  - Validate: x, y ≥ 0; x + width ≤ video_width; y + height ≤ video_height — báo lỗi ngay trên UI nếu vượt biên.

### 5.4 SceneExtractionService
- **Input**: video_path, interval_seconds, crop_rect (hoặc null nếu full frame), output_dir, output_format, on_progress
- **Output**: danh sách các file ảnh đã tạo, theo đúng thứ tự thời gian
- **Trách nhiệm**: build lệnh FFmpeg tương ứng và chạy qua subprocess:
  - Nếu full frame: dùng filter lấy mẫu theo tần suất tương ứng `interval_seconds` (ví dụ: 1 ảnh mỗi N giây)
  - Nếu crop: áp filter crop theo `crop_rect` TRƯỚC filter lấy mẫu (thứ tự filter không ảnh hưởng kết quả cuối, nhưng nên áp dụng crop trước để dễ debug hình ảnh trung gian)
  - Đặt tên file output theo mẫu số thứ tự bắt đầu từ 1 (không phải 0)
  - Parse output/stderr của FFmpeg để tính % tiến độ dựa trên duration video, gọi `on_progress`

### 5.5 OutputPackager
- **Input**: danh sách file ảnh đã trích, output_dir, zip_after_done (bool)
- **Trách nhiệm**:
  - Đảm bảo tên file đúng thứ tự: `1.png, 2.png, ..., n.png` (không có số 0 đứng đầu kiểu `0001.png` trừ khi người dùng yêu cầu, vì spec gốc yêu cầu đúng "1 2 3...n")
  - Nếu `zip_after_done = true`: nén toàn bộ thư mục ảnh thành 1 file `.zip` cùng tên với video
  - Xoá video gốc nếu `keep_source_video = false`

---

## 6. UI wireframe (mô tả, không phải code)

```
┌─────────────────────────────────────────────┐
│ URL video: [___________________] [Tải thông tin] │
│                                               │
│ Tiêu đề: ...      Thời lượng: 1h 32m          │
│ [thumbnail]                                   │
│                                               │
│ Chất lượng tải: [720p ▾]                      │
│                                               │
│ Khoảng thời gian:  ( ) 2s ( ) 5s ( ) 10s ( ) 60s │
│                     ( ) Tuỳ chỉnh: [___] giây  │
│                                               │
│ Chế độ chụp:  ( ) Toàn màn hình               │
│               (•) Vùng crop cố định            │
│                                               │
│   ┌───────────────────────────┐               │
│   │      [ảnh preview có      │  X: [___]     │
│   │       khung kéo chọn]     │  Y: [___]     │
│   │                           │  W: [___]     │
│   └───────────────────────────┘  H: [___]     │
│                                               │
│ Thư mục lưu: [_______________] [Chọn...]      │
│ [ ] Nén thành .zip sau khi xong                │
│ [ ] Giữ lại video gốc                          │
│                                               │
│              [▶ Bắt đầu trích ảnh]            │
│  ████████████░░░░░░░░░░  62%  (đang trích ảnh) │
└─────────────────────────────────────────────┘
```

---

## 7. Xử lý lỗi & edge case cần lường trước

- Link không hợp lệ / video riêng tư / đã bị xoá → báo lỗi rõ ràng ngay ở bước lấy thông tin, không cho tiếp tục
- Mạng chậm/đứt giữa lúc tải → cho phép resume hoặc báo lỗi rõ, không để app treo
- `interval_seconds` lớn hơn duration video → báo lỗi, chỉ trích được 1 ảnh
- Crop vượt quá kích thước video thực tế (VD: preview hiển thị sai tỉ lệ) → validate trước khi cho chạy FFmpeg, không để FFmpeg lỗi giữa chừng
- Ổ đĩa không đủ dung lượng cho cả video tạm + toàn bộ ảnh xuất ra (video 1-2 tiếng ở 720p có thể vài trăm MB đến vài GB, video 2h chia mốc 2s = 3600 ảnh PNG có thể vài trăm MB thêm) → kiểm tra dung lượng trống trước khi bắt đầu
- FFmpeg/yt-dlp binary không có sẵn trên máy người dùng (nếu không đóng gói kèm) → kiểm tra tồn tại lúc khởi động app, hướng dẫn cài đặt nếu thiếu

---

## 8. Hiệu năng & giới hạn cần lưu ý khi triển khai

- Video 2 giờ, mốc 2s = 3600 ảnh PNG → cân nhắc mặc định output là JPG chất lượng cao (giảm dung lượng đáng kể) hoặc cho người dùng chọn định dạng
- Chạy FFmpeg là tác vụ blocking, cần chạy trong thread riêng (không block UI thread) để progress bar mượt
- Nên cho phép huỷ tác vụ đang chạy (cả download lẫn extraction) — người dùng có thể đổi ý giữa video 2 tiếng

---

## 9. Cấu trúc thư mục project đề xuất

```
youtube-scene-capture/
├── main.py                    # entry point, khởi tạo UI
├── services/
│   ├── video_info_service.py
│   ├── video_download_service.py
│   ├── preview_service.py
│   ├── scene_extraction_service.py
│   └── output_packager.py
├── ui/
│   ├── main_window.py
│   └── crop_selector_widget.py
├── models/
│   └── capture_config.py      # dataclass CaptureConfig ở mục 4
└── requirements.txt
```

## 10. Thư viện phụ thuộc chính

- `yt-dlp` — tải video
- `ffmpeg` (binary, không phải thư viện Python) — trích/crop scene
- `PySide6` — GUI
- `Pillow` (tuỳ chọn) — nếu cần xử lý ảnh preview thêm ngoài FFmpeg
