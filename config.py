import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
WATCH_DIR = BASE_DIR / "PRAVACHAN"
TEMP_DIR = BASE_DIR / "temp_videos"
DB_PATH = BASE_DIR / "pravachan.db"

# YouTube OAuth 2.0 Credentials
CLIENT_SECRETS_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"

# Supported File Formats
SUPPORTED_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".opus", ".ogg"}
THUMBNAIL_FILENAMES = ["thumbnail.jpg", "thumbnail.jpeg", "thumbnail.png", "cover.jpg", "cover.png"]

# YouTube Upload Settings
# Allowed values: 'private', 'unlisted', 'public'
# NOTE: Unverified YouTube API projects MUST use 'private' to prevent Google ToS bans.
DEFAULT_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "private")

# Category 22 = People & Blogs; 27 = Education; 29 = Nonprofits & Activism
DEFAULT_CATEGORY_ID = "22"

# Default tags added to uploaded videos
DEFAULT_TAGS = ["Pravachan", "Katha", "Spiritual", "Devotional"]

# YouTube API Scopes required for upload, thumbnail, and playlist management
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

# Rate Limit & Safety Settings
# Default daily YouTube API quota is 10,000 units.
# 1 Video (~1600) + 1 Thumbnail (50) + 1 PlaylistItem (50) = ~1700 units per video.
# 5 uploads = 8,500 units (leaves safety margin for token refreshes and queries).
MAX_UPLOADS_PER_DAY = int(os.getenv("MAX_UPLOADS_PER_DAY", "5"))

# Pacing delay between consecutive uploads (seconds) to prevent automated bot detection
INTER_UPLOAD_DELAY_SECONDS = int(os.getenv("INTER_UPLOAD_DELAY_SECONDS", "30"))

# Scheduler Settings
DEFAULT_INTERVAL_MINUTES = 10

# Upload chunk size (10MB) for resumable uploads
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024

# Ensure essential directories exist
TEMP_DIR.mkdir(parents=True, exist_ok=True)
WATCH_DIR.mkdir(parents=True, exist_ok=True)
