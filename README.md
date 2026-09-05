# 🎙️ Pravachan Automated YouTube Uploader

An automated, local-first Python engine designed to scan audio discourse folders, combine each track with its folder's thumbnail into an optimized MP4 video, upload it directly to YouTube with resumable uploads, set custom thumbnails, and automatically group videos into dedicated playlists.

---

## 📋 Features

- 🔄 **Automated Folder Monitoring**: Continuously scans local folders or Google Drive synced directories for new audio files.
- 🛡️ **Zero Duplicate Uploads**: Uses SQLite (`pravachan.db`) and SHA-256 file hashing to track uploaded files and prevent accidental re-uploads.
- ⚡ **Optimized FFmpeg Video Encoding**: Bundles zero-setup FFmpeg via `imageio-ffmpeg` using `-tune stillimage` and H.264 encoding to produce lightweight, high-fidelity MP4 videos in seconds.
- 🌐 **Devanagari & Unicode Support**: Full native support for Hindi, Marathi, Sanskrit, and regional language titles and filenames without encoding errors on Windows.
- 🔢 **Natural Number Sorting**: Automatically orders multi-part series correctly (e.g., Part 1, Part 2, ..., Part 10) instead of alphabetical sorting.
- 🚀 **Resumable Chunked Uploads**: Implements Google API resumable uploads with exponential backoff to survive temporary network drops.
- 🖼️ **Automatic Custom Thumbnails**: Uploads and sets the folder's `thumbnail.jpg` as the YouTube video thumbnail.
- 📑 **Smart Playlist Management**: Automatically finds or creates a YouTube playlist matching the subfolder name and assigns each video to it.
- 🚦 **Quota-Aware**: Detects YouTube Data API daily limits (`quotaExceeded`) and pauses gracefully to protect your quota.
- 🛠️ **Bulk Publishing Utility**: Includes `publish_videos.py` to switch previously uploaded private videos to public in one click.

---

## 🏗️ Architecture

```text
Google Drive / Local Storage
        │
        ▼
   Audio Folders  (e.g., PRAVACHAN/NANASAHEB DEV MAHTI/)
        │  - thumbnail.jpg
        │  - Part 1.m4a, Part 2.m4a
        ▼
   Python Scanner (uploader.py)
        │
        ├── Check SQLite Database (pravachan.db) ──> Skip if already uploaded
        │
        ├── FFmpeg Helper ──> Encode thumbnail + audio -> MP4
        │
        ├── YouTube Client ──> Resumable video upload (OAuth 2.0)
        │
        ├── Set Custom Thumbnail ──> Uploads thumbnail.jpg
        │
        ├── Playlist Manager ──> Create or find playlist & add video
        │
        └── SQLite Tracker ──> Mark as COMPLETED & clean up temp MP4
```

---

## 📂 Folder Structure Convention

Organize your discourse audio files inside the `PRAVACHAN` folder:

```text
Youtube_Uploader/
│
├── PRAVACHAN/
│   ├── Bhagwat Katha 2026/
│   │   ├── thumbnail.jpg
│   │   ├── 01 - Introduction.m4a
│   │   ├── 02 - Krishna Janma.m4a
│   │   └── 03 - Gopi Prem.m4a
│   │
│   └── NANASAHEB DEV MAHTI/
│       ├── thumbnail.jpg
│       ├── नानासाहेब देव महती भाग 1.m4a
│       └── नानासाहेब देव महती भाग 2.m4a
```

- **Thumbnail**: Name your image `thumbnail.jpg`, `thumbnail.png`, or `cover.jpg`.
- **Audio Formats**: Supports `.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.opus`, `.ogg`.
- **Playlist Title**: The folder name (e.g. `NANASAHEB DEV MAHTI`) automatically becomes the YouTube Playlist title.
- **Video Title**: Cleaned from the audio filename (strips file extension and collapses irregular spaces).

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/Yashparmar1125/youtube_uploader_agcl.git
cd youtube_uploader_agcl
```

### 2. Install Dependencies
Make sure you have **Python 3.10+** installed (with *"Add Python to PATH"* checked).

```bash
pip install -r requirements.txt
```
*(FFmpeg is automatically bundled via `imageio-ffmpeg`; no separate manual installation required).*

### 3. Google Cloud YouTube API Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **YouTube Data API v3**.
3. Under **OAuth consent screen**:
   - Set user type to **External**.
   - Add scopes: `.../auth/youtube.upload` and `.../auth/youtube`.
   - Add your Gmail address under **Test users**.
4. Under **Credentials**:
   - Create **OAuth client ID** (Application type: **Desktop app**).
   - Click **Download JSON**.
5. Rename the downloaded file to **`client_secret.json`** and save it in the project root directory.

> **Note on Thumbnails**: YouTube requires your channel to be phone-verified under [YouTube Feature Eligibility](https://www.youtube.com/features) to enable custom thumbnails.

---

## 💻 Usage

### Dry-Run Test (Safe Simulation)
Simulate scanning without rendering videos or consuming YouTube API quota:
```bash
python uploader.py --dry-run
```

### Run Once
Scan folders, encode any new audio files, and upload them to YouTube:
```bash
python uploader.py --run-once
```
*(On your first run, a browser window will open asking you to sign in with your Google Account once. Subsequent runs authenticate silently in the background).*

### Continuous Monitor
Check for new audio files automatically on an interval (e.g., every 10 minutes):
```bash
python uploader.py --loop --interval 10
```

### Windows Batch Launcher
Double-click **`run_uploader.bat`** in File Explorer for an interactive menu.

### Bulk Publish Utility
If videos were previously uploaded as private or unlisted, change them all to public at once:
```bash
python publish_videos.py
```

---

## ⏰ Automated Scheduling

### Windows Task Scheduler (Runs Silently in Background)
1. Open Windows Task Scheduler (`taskschd.msc`).
2. Click **Create Task**.
3. **General Tab**: Name the task `YouTube Uploader` and select `Run only when user is logged on`.
4. **Triggers Tab**: Add a trigger for **Daily**, repeat every **10 minutes**, indefinitely.
5. **Actions Tab**:
   - Action: **Start a program**
   - Program/script: `pythonw.exe` *(runs invisibly without popping up a console window)*
   - Add arguments: `uploader.py --run-once`
   - Start in: `C:\path\to\youtube_uploader_agcl`

### Linux / macOS Cron
```cron
*/10 * * * * cd /path/to/youtube_uploader_agcl && /usr/bin/python3 uploader.py --run-once >> uploader.log 2>&1
```

---

## ⚙️ Configuration (`config.py`)

| Setting | Default | Description |
| :--- | :--- | :--- |
| `WATCH_DIR` | `BASE_DIR / "PRAVACHAN"` | Folder to monitor (can point to Google Drive) |
| `TEMP_DIR` | `BASE_DIR / "temp_videos"` | Staging directory for rendered MP4s |
| `DB_PATH` | `BASE_DIR / "pravachan.db"` | SQLite database file path |
| `DEFAULT_PRIVACY` | `"public"` | Upload visibility (`public`, `unlisted`, or `private`) |
| `DEFAULT_CATEGORY_ID` | `"22"` | YouTube Category ID (`22` = People & Blogs) |
| `DEFAULT_TAGS` | `["Pravachan", "Katha", ...]` | Default YouTube tags |

---

## 📊 YouTube API Quota Information

- Default free YouTube Data API quota: **10,000 units/day** (resets at midnight Pacific Time).
- Uploading a video costs **1,600 units**.
- Playlist and thumbnail operations cost **50 units each**.
- **Daily capacity**: ~5 to 6 videos per day on a single free Google Cloud project.
- If daily quota is exhausted, the engine safely records progress in SQLite and resumes on the next scheduled run once quota resets.

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).
