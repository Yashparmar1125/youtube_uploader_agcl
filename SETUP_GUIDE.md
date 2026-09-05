# Pravachan Automated YouTube Uploader - Setup & Usage Guide

This project automatically scans audio folders, combines each audio track with its folder's thumbnail into an optimized MP4 video, uploads it to YouTube with resumable chunked uploads, sets the custom thumbnail, and creates/assigns the video to a dedicated playlist named after the folder.

---

## 1. Directory Structure

Place your Pravachan folders inside `PRAVACHAN/` (or sync your Google Drive to this folder):

```text
c:\Users\Yash\VS_PROJECTS\Youtube_Uploader\
│
├── PRAVACHAN/
│   ├── NANASAHEB DEV MAHTI/
│   │   ├── thumbnail.jpg
│   │   ├── नानासाहेब देव महती भाग   1.m4a
│   │   ├── नानासाहेब देव महती भाग   2.m4a
│   │   └── नानासाहेब देव महती भाग   3.m4a
│   │
│   └── Ram Katha 2026/
│       ├── thumbnail.jpg
│       ├── 01 - Intro.mp3
│       └── 02 - Katha.mp3
```

- **Thumbnail**: Name it `thumbnail.jpg`, `thumbnail.png`, or `cover.jpg`.
- **Audio Formats**: Supports `.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.opus`.
- **Playlist Title**: The folder name (e.g. `NANASAHEB DEV MAHTI`) automatically becomes the YouTube Playlist title.
- **Video Title**: Cleaned from the audio filename (strips extension and normalizes irregular spacing).

---

## 2. Google Cloud Setup (Getting `client_secret.json`)

To allow the script to upload videos to your YouTube channel:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Pravachan-Uploader`).
3. In the search bar at the top, search for **YouTube Data API v3** and click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Select **User Type**: **External** (click *Create*).
   - App Name: `Pravachan Uploader`.
   - User support email: Select your email.
   - Developer contact email: Enter your email.
   - Click **Save and Continue**.
   - Under **Scopes**: Click *Add or Remove Scopes*, search for `YouTube Data API v3`, and select:
     - `.../auth/youtube.upload` (Manage your YouTube videos)
     - `.../auth/youtube` (Manage your YouTube account)
   - Click **Update** -> **Save and Continue**.
   - Under **Test Users**: Click **+ Add Users** and enter the Gmail address that owns or manages your YouTube channel.
   - Click **Save and Continue**.
5. Create **Credentials**:
   - Go to **Credentials** in the left sidebar.
   - Click **+ Create Credentials** -> **OAuth client ID**.
   - Application type: **Desktop app**.
   - Name: `Pravachan Desktop Client`.
   - Click **Create**.
   - Click **Download JSON** on the created client ID.
6. Rename the downloaded file to **`client_secret.json`** and place it in the project root folder:
   `c:\Users\Yash\VS_PROJECTS\Youtube_Uploader\client_secret.json`

---

## 3. First-Time Channel Verification (for Thumbnails)

YouTube requires your channel to be phone-verified to enable custom thumbnails.
- Check eligibility at: [YouTube Feature Eligibility](https://www.youtube.com/features)
- Under "Intermediate features" (includes custom thumbnails and videos longer than 15 min), ensure it is verified with a phone number.

---

## 4. Running the Uploader

### Option A: Using the Windows Batch Runner
Double-click `run_uploader.bat` in File Explorer:
- Choose `1` for single run (processes new files and closes).
- Choose `2` for continuous monitoring (checks every 10 minutes).
- Choose `3` for dry-run simulation.

### Option B: Command Line
Open PowerShell or Command Prompt in the project folder:

```powershell
# Test without uploading (simulates scan & title detection)
python uploader.py --dry-run

# Run once (processes pending files and uploads as public)
python uploader.py --run-once

# Run continuously every 10 minutes
python uploader.py --loop --interval 10

# Bulk-update existing private videos to public:
python publish_videos.py
```

### First Run Authorization
On the very first run, a browser tab will open asking you to sign in with your Google Account and approve permissions.
Once approved, a `token.json` file is automatically created. From that moment on, all runs (including background tasks) will authenticate automatically without any user interaction.

---

## 5. Automated Scheduling via Windows Task Scheduler

To have Windows run the uploader automatically in the background every 10 or 15 minutes:

1. Press `Win + R`, type `taskschd.msc`, and press Enter.
2. Click **Create Task** in the right pane.
3. **General Tab**:
   - Name: `Pravachan YouTube Uploader`.
   - Check: *Run whether user is logged on or not* (or *Run only when user is logged on*).
4. **Triggers Tab**:
   - Click **New...**
   - Begin the task: *On a schedule*.
   - Daily -> Repeat task every: **10 minutes** for a duration of: **Indefinitely**.
5. **Actions Tab**:
   - Click **New...**
   - Action: *Start a program*.
   - Program/script: `pythonw.exe` (or `C:\Python314\pythonw.exe`).
   - Add arguments: `uploader.py --run-once`
   - Start in: `c:\Users\Yash\VS_PROJECTS\Youtube_Uploader`
6. Click **OK** to save.

---

## 6. YouTube Daily Quota Reference

- YouTube Data API provides **10,000 free quota units** daily (resets at midnight Pacific Time / ~12:30 PM IST).
- A video upload costs **1,600 units**.
- Thumbnail upload and playlist additions cost **50 units each**.
- **Daily capacity**: ~5 to 6 videos per day on the default free tier.
- If you exceed the daily limit, the uploader automatically detects it, saves progress in `pravachan.db`, and safely resumes when quota resets.
