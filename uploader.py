import os
import re
import sys
import time
import logging
import argparse
from pathlib import Path
from typing import List, Optional, Tuple

import config
import db
import ffmpeg_helper
from youtube_client import YouTubeClient, YouTubeQuotaExceededError

# Configure Windows console for UTF-8 output to support Hindi/Marathi characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configure Logging to both Console and File
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.BASE_DIR / "uploader.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def natural_sort_key(s: Path):
    """Sort strings containing numbers in human order (e.g. 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s.name)]

def clean_title(filename: str) -> str:
    """Removes extension and normalizes multiple spaces."""
    stem = Path(filename).stem
    # Replace multiple spaces with a single space
    cleaned = re.sub(r'\s+', ' ', stem).strip()
    return cleaned

def find_thumbnail(folder_path: Path) -> Optional[Path]:
    """Finds a thumbnail image in the folder."""
    # First, look for standard names
    for name in config.THUMBNAIL_FILENAMES:
        candidate = folder_path / name
        if candidate.exists() and candidate.is_file():
            return candidate

    # Fallback: find any jpg or png in the directory
    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            return file

    return None

def find_audio_files(folder_path: Path) -> List[Path]:
    """Returns all supported audio files in the folder sorted naturally."""
    audio_files = []
    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() in config.SUPPORTED_AUDIO_EXTENSIONS:
            audio_files.append(file)
    audio_files.sort(key=natural_sort_key)
    return audio_files

def generate_description(title: str, folder_name: str) -> str:
    """Generates standard video description."""
    return (
        f"{title}\n\n"
        f"Series: {folder_name}\n\n"
        "Uploaded via Pravachan Automated Uploader."
    )

def process_single_audio(
    audio_path: Path,
    thumbnail_path: Path,
    folder_name: str,
    youtube: Optional[YouTubeClient],
    privacy_status: str,
    dry_run: bool = False
) -> bool:
    """
    Processes one audio file:
    - Calculates hash & checks if already uploaded
    - Encodes MP4 with FFmpeg
    - Uploads to YouTube
    - Sets thumbnail
    - Adds to playlist
    - Updates SQLite database
    """
    file_size = audio_path.stat().st_size
    file_hash = db.compute_file_hash(audio_path)
    title = clean_title(audio_path.name)

    # Check if already processed
    if db.is_file_processed(file_hash):
        logger.info(f"Skipping already uploaded file: '{audio_path.name}' (Hash: {file_hash[:8]}...)")
        return False

    if dry_run:
        logger.info(f"[DRY-RUN] Found new audio: '{title}' [{folder_name}]")
        logger.info(f"[DRY-RUN] Would encode '{audio_path.name}' + '{thumbnail_path.name}' -> MP4")
        logger.info(f"[DRY-RUN] Would upload to YouTube with title: '{title}' ({privacy_status})")
        logger.info(f"[DRY-RUN] Would add to playlist: '{folder_name}'")
        return True

    db.register_file(audio_path, file_hash, file_size, folder_name, title)
    logger.info(f"==> Found new audio to process: '{title}' [{folder_name}]")

    # Temporary MP4 output path
    temp_mp4 = config.TEMP_DIR / f"{file_hash[:16]}.mp4"

    try:
        # Step 1: Render MP4
        db.update_status(file_hash, "ENCODING")
        ffmpeg_helper.convert_audio_to_video(thumbnail_path, audio_path, temp_mp4)
        db.update_status(file_hash, "ENCODED")

        # Step 2: Upload Video to YouTube
        db.update_status(file_hash, "UPLOADING")
        description = generate_description(title, folder_name)
        video_id = youtube.upload_video(
            video_path=temp_mp4,
            title=title,
            description=description,
            privacy_status=privacy_status
        )

        # Step 3: Set Custom Thumbnail
        youtube.set_thumbnail(video_id, thumbnail_path)

        # Step 4: Add to Playlist
        playlist_id = youtube.get_or_create_playlist(
            playlist_title=folder_name,
            privacy_status=privacy_status
        )
        youtube.add_video_to_playlist(playlist_id, video_id)

        # Step 5: Mark Completed in SQLite DB
        db.update_status(
            file_hash=file_hash,
            status="COMPLETED",
            youtube_video_id=video_id,
            youtube_playlist_id=playlist_id
        )
        logger.info(f"[SUCCESS] Finished processing '{title}' -> https://youtu.be/{video_id}")
        return True

    except YouTubeQuotaExceededError:
        logger.error("YouTube daily quota limit reached! Pausing remaining uploads until tomorrow.")
        db.update_status(file_hash, "FAILED", error_message="YouTube quota exceeded")
        raise

    except Exception as e:
        logger.error(f"Error processing '{title}': {e}", exc_info=True)
        db.update_status(file_hash, "FAILED", error_message=str(e))
        return False

    finally:
        # Step 6: Clean up temporary MP4 file
        if temp_mp4.exists():
            ffmpeg_helper.cleanup_temp_video(temp_mp4)

def scan_and_upload(
    youtube: Optional[YouTubeClient],
    privacy_status: str,
    dry_run: bool = False
) -> int:
    """Scans all subfolders in WATCH_DIR and processes any pending audio files."""
    db.init_db()
    total_processed = 0

    if not config.WATCH_DIR.exists():
        logger.warning(f"Watch directory does not exist: {config.WATCH_DIR}")
        return 0

    # Scan subdirectories
    subdirs = [d for d in config.WATCH_DIR.iterdir() if d.is_dir()]
    if not subdirs:
        logger.info(f"No subfolders found in {config.WATCH_DIR}")
        return 0

    for folder in subdirs:
        folder_name = folder.name
        thumbnail = find_thumbnail(folder)
        audio_files = find_audio_files(folder)

        if not audio_files:
            continue

        if not thumbnail:
            logger.warning(
                f"Folder '{folder_name}' has {len(audio_files)} audio file(s) but NO thumbnail image found! "
                f"Please add 'thumbnail.jpg' to '{folder_name}'."
            )
            continue

        logger.info(f"Scanning '{folder_name}': Found {len(audio_files)} audio file(s) and thumbnail '{thumbnail.name}'.")

        for audio in audio_files:
            try:
                processed = process_single_audio(
                    audio_path=audio,
                    thumbnail_path=thumbnail,
                    folder_name=folder_name,
                    youtube=youtube,
                    privacy_status=privacy_status,
                    dry_run=dry_run
                )
                if processed:
                    total_processed += 1
            except YouTubeQuotaExceededError:
                return total_processed

    return total_processed

def main():
    parser = argparse.ArgumentParser(description="Pravachan Automated YouTube Uploader")
    parser.add_argument("--run-once", action="store_true", help="Run scan once and exit")
    parser.add_argument("--loop", action="store_true", help="Run continuously on an interval")
    parser.add_argument("--interval", type=int, default=config.DEFAULT_INTERVAL_MINUTES, help="Interval in minutes for continuous loop")
    parser.add_argument("--dry-run", action="store_true", help="Simulate folder scanning and video detection without uploading")
    parser.add_argument("--privacy", type=str, choices=["private", "unlisted", "public"], default=config.DEFAULT_PRIVACY, help="YouTube upload privacy status")

    args = parser.parse_args()

    logger.info("==========================================")
    logger.info("Starting Pravachan YouTube Uploader Engine")
    logger.info(f"Watch Directory: {config.WATCH_DIR}")
    logger.info(f"Database Path:   {config.DB_PATH}")
    logger.info(f"Privacy Mode:    {args.privacy}")
    logger.info(f"Dry Run Mode:    {args.dry_run}")
    logger.info("==========================================")

    # Initialize YouTube client only if not in dry-run mode
    youtube = None
    if not args.dry_run:
        try:
            youtube = YouTubeClient()
            youtube.authenticate()
        except FileNotFoundError as e:
            logger.error(str(e))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to authenticate with YouTube: {e}", exc_info=True)
            sys.exit(1)

    if args.loop:
        logger.info(f"Entering continuous loop. Checking every {args.interval} minutes. Press Ctrl+C to stop.")
        try:
            while True:
                logger.info("Running scheduled scan...")
                scan_and_upload(youtube, args.privacy, dry_run=args.dry_run)
                logger.info(f"Scan complete. Sleeping for {args.interval} minutes...")
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            logger.info("Uploader stopped by user.")
    else:
        # Default is run-once
        count = scan_and_upload(youtube, args.privacy, dry_run=args.dry_run)
        logger.info(f"Run-once completed. Processed {count} file(s).")

if __name__ == "__main__":
    main()
