# Complete Guide: Setting Up YouTube Uploader on a Different Machine

This guide explains step-by-step how to move and run this automated YouTube uploader on another computer (laptop, desktop, or dedicated server).

---

## 1. What Files to Copy to the New Machine

Copy the `Youtube_Uploader` folder to the new machine. Make sure it includes these key files:

| File / Folder | Needed? | Description |
| :--- | :--- | :--- |
| `uploader.py` | **Yes** | Main script |
| `config.py` | **Yes** | Settings (configured to **public** uploads) |
| `db.py` | **Yes** | SQLite database manager |
| `ffmpeg_helper.py` | **Yes** | Video generator |
| `youtube_client.py` | **Yes** | YouTube API communication |
| `publish_videos.py` | **Yes** | Tool to change existing videos to public |
| `run_uploader.bat` | **Yes** | One-click launcher for Windows |
| `requirements.txt` | **Yes** | List of Python dependencies |
| **`client_secret.json`** | **CRITICAL** | Your Google Cloud OAuth credentials |
| **`token.json`** | **RECOMMENDED** | **If you copy this file, you do NOT even need to log in again on the new machine!** It carries over your authenticated session. |
| **`pravachan.db`** | **RECOMMENDED** | Keeps the history of already uploaded videos so the new machine will never re-upload them. |
| `PRAVACHAN/` | Optional | Your audio folders. On the new machine, this can be synced from Google Drive Desktop. |

*(You do **not** need to copy `temp_videos/` or `__pycache__` folders; the script creates them automatically).*

---

## 2. Setup on the New Machine

### Step 1: Install Python
1. Download Python for Windows from [python.org/downloads](https://www.python.org/downloads/) (Python 3.10, 3.11, 3.12, 3.13, or 3.14).
2. Run the installer.
3. > [!IMPORTANT]
   > On the very first installer screen, **CHECK the box**:
   > ☑ **"Add python.exe to PATH"**
4. Click **Install Now** and finish the setup.

---

### Step 2: Install Required Libraries
1. Open **Command Prompt** (`cmd`) or **PowerShell**.
2. Navigate to your project folder:
   ```cmd
   cd c:\path\to\Youtube_Uploader
   ```
3. Install all required dependencies by running:
   ```cmd
   pip install -r requirements.txt
   ```
   *(Note: This automatically includes `imageio-ffmpeg`, which bundles the FFmpeg executable. You do **not** need to manually download or configure FFmpeg).*

---

### Step 3: Verify the Setup
Run a quick dry-run test:
```cmd
python uploader.py --dry-run
```
You should see:
```text
Watch Directory: ...\PRAVACHAN
Privacy Mode:    public
Dry Run Mode:    True
Found audio file(s) and thumbnail...
```

---

### Step 4: First Real Run
- If you copied **`token.json`**: The script will immediately authenticate without asking for anything.
- If you did **not** copy `token.json`: A web browser tab will open once asking you to log in to your Google Account and click **Allow**. It will create `token.json` automatically for all future runs.

Run the uploader:
```cmd
python uploader.py --run-once
```
or double-click **`run_uploader.bat`** and select **`1`**.

---

## 3. How to Automate on the New Machine

You have two choices for automatic background execution:

### Choice A: Windows Task Scheduler (Recommended - Runs Silently)
Runs in the background every 10 minutes even if no window is open:

1. Press `Win + R`, type **`taskschd.msc`**, and press Enter.
2. In the right pane, click **Create Task**.
3. **General Tab**:
   - Name: `Pravachan YouTube Uploader`
   - Check: `Run only when user is logged on` (or `Run whether user is logged on or not`).
4. **Triggers Tab**:
   - Click **New...**
   - Begin the task: **On a schedule**.
   - Select **Daily**.
   - Under Advanced settings, check: **Repeat task every:** `10 minutes` for a duration of: `Indefinitely`.
   - Click **OK**.
5. **Actions Tab**:
   - Click **New...**
   - Action: **Start a program**
   - Program/script: `pythonw.exe` *(Note: `pythonw.exe` runs completely silently in the background without popping up a black console window!)*
     - Path is typically: `C:\Python314\pythonw.exe` or `pythonw.exe`
   - Add arguments: `uploader.py --run-once`
   - Start in: `C:\path\to\Youtube_Uploader` *(Your project directory)*
   - Click **OK**.
6. Click **OK** to save the task.

---

### Choice B: Continuous Loop Mode
If you prefer to keep a lightweight monitor running in a minimized window:
- Double-click **`run_uploader.bat`** and choose **`2`**.
- Or run in terminal:
  ```cmd
  python uploader.py --loop --interval 10
  ```
This script will check the folders every 10 minutes and upload any newly added audio tracks.

---

## 4. Setting Up on Linux or Mac (If Applicable)

If the different machine runs Linux (e.g. Ubuntu server) or macOS:

1. Install Python 3 and FFmpeg:
   - Ubuntu/Debian: `sudo apt update && sudo apt install -y python3 python3-pip ffmpeg`
   - Mac: `brew install python ffmpeg`
2. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
3. Set up a cron job (`crontab -e`):
   ```cron
   */10 * * * * cd /home/username/Youtube_Uploader && /usr/bin/python3 uploader.py --run-once >> /home/username/Youtube_Uploader/uploader.log 2>&1
   ```

---

## 5. Helpful Commands & Utilities

* **Change Existing Private Videos to Public**:
  Run this anytime to bulk-publish previously uploaded private videos:
  ```cmd
  python publish_videos.py
  ```

* **Test Without Uploading**:
  ```cmd
  python uploader.py --dry-run
  ```

* **Check Upload Logs**:
  All upload activity, progress percentages, video links, and errors are saved in `uploader.log`.
