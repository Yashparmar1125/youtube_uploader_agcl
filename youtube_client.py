import os
import time
import random
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import (
    CLIENT_SECRETS_FILE,
    TOKEN_FILE,
    YOUTUBE_SCOPES,
    UPLOAD_CHUNK_SIZE,
    DEFAULT_PRIVACY,
    DEFAULT_CATEGORY_ID,
    DEFAULT_TAGS
)
import db

logger = logging.getLogger(__name__)

class YouTubeQuotaExceededError(Exception):
    """Raised when YouTube API quota has been exhausted for the day."""
    pass

class YouTubeClient:
    def __init__(self):
        self.service: Optional[Resource] = None
        self.creds: Optional[Credentials] = None

    def _save_token(self) -> None:
        """Persists the current credentials to token.json."""
        if self.creds:
            with open(TOKEN_FILE, "w", encoding="utf-8") as token_out:
                token_out.write(self.creds.to_json())
            logger.info("Updated and saved active token to token.json")

    def ensure_valid_credentials(self) -> None:
        """
        Validates that credentials are fully active and refreshed before any call.
        If expired, refreshes automatically and persists the new token.
        If refresh fails (e.g. revoked/invalid grant), triggers re-authentication.
        """
        if not self.creds:
            self.authenticate()
            return

        if not self.creds.valid or self.creds.expired:
            logger.info("OAuth access token expired or nearing expiry. Refreshing...")
            try:
                self.creds.refresh(Request())
                self._save_token()
                self.service = build("youtube", "v3", credentials=self.creds)
                logger.info("Successfully refreshed OAuth access token.")
            except Exception as e:
                logger.warning(f"Token refresh failed ({e}). Re-initiating OAuth authentication...")
                self.force_refresh_or_reauth()

    def force_refresh_or_reauth(self) -> None:
        """Forces an immediate refresh of credentials or launches re-authorization."""
        try:
            if self.creds and self.creds.refresh_token:
                logger.info("Attempting to refresh token using refresh_token...")
                self.creds.refresh(Request())
                self._save_token()
                self.service = build("youtube", "v3", credentials=self.creds)
                logger.info("Token refreshed successfully.")
                return
        except Exception as e:
            logger.warning(f"Could not refresh token: {e}. Token may have been revoked or expired.")

        # If refresh fails, wipe stale token and re-authenticate
        if TOKEN_FILE.exists():
            try:
                TOKEN_FILE.unlink(missing_ok=True)
                logger.info("Removed stale token.json.")
            except Exception:
                pass
        self.creds = None
        self.service = None
        self.authenticate()

    def authenticate(self) -> Resource:
        """
        Authenticates with YouTube API using OAuth 2.0.
        Loads existing token from token.json or initiates browser flow.
        """
        self.creds = None
        if TOKEN_FILE.exists():
            try:
                self.creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), YOUTUBE_SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load existing token from {TOKEN_FILE}: {e}")

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                logger.info("Refreshing expired YouTube OAuth access token...")
                try:
                    self.creds.refresh(Request())
                    self._save_token()
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}. Initiating fresh login.")
                    self.creds = None

            if not self.creds:
                if not CLIENT_SECRETS_FILE.exists():
                    raise FileNotFoundError(
                        f"OAuth credentials file not found: '{CLIENT_SECRETS_FILE}'.\n"
                        "Please download client_secret.json from Google Cloud Console "
                        "and place it in the project root directory. See SETUP_GUIDE.md for instructions."
                    )
                logger.info("Opening browser for one-time YouTube authorization...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CLIENT_SECRETS_FILE),
                    YOUTUBE_SCOPES
                )
                self.creds = flow.run_local_server(port=0)
                self._save_token()

        self.service = build("youtube", "v3", credentials=self.creds)
        return self.service

    def get_service(self) -> Resource:
        self.ensure_valid_credentials()
        return self.service

    def execute_api_call(self, request_fn: Callable[[], Any], max_retries: int = 3) -> Any:
        """
        Executes an API call with automatic handling of:
        - 401 Unauthorized -> refreshes token and retries
        - 403 quotaExceeded -> raises YouTubeQuotaExceededError
        - 5xx transient server errors -> exponential backoff retry
        """
        for attempt in range(max_retries):
            try:
                self.ensure_valid_credentials()
                return request_fn()
            except HttpError as e:
                if e.resp.status == 401 and attempt < max_retries - 1:
                    logger.warning(f"Received 401 Unauthorized (attempt {attempt + 1}/{max_retries}). Forcing token refresh...")
                    self.force_refresh_or_reauth()
                    continue
                elif e.resp.status == 403:
                    content_str = e.content.decode("utf-8", errors="ignore")
                    if "quotaExceeded" in content_str:
                        logger.error("Daily YouTube API quota exceeded.")
                        raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
                    raise
                elif e.resp.status in [500, 502, 503, 504] and attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) + random.random()
                    logger.warning(f"Server error {e.resp.status}. Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                    continue
                raise
            except Exception as e:
                if "invalid_grant" in str(e).lower() and attempt < max_retries - 1:
                    logger.warning("Detected invalid_grant error. Re-authenticating...")
                    self.force_refresh_or_reauth()
                    continue
                raise

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: str = DEFAULT_PRIVACY
    ) -> str:
        """
        Uploads an MP4 file to YouTube using resumable chunked upload.
        Includes robust 401 token refresh and network recovery.
        """
        self.ensure_valid_credentials()
        youtube = self.get_service()
        if tags is None:
            tags = DEFAULT_TAGS

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit is 100 chars
                "description": description,
                "tags": tags,
                "categoryId": DEFAULT_CATEGORY_ID
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=UPLOAD_CHUNK_SIZE,
            resumable=True
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        logger.info(f"Starting upload for '{title}' ({privacy_status})...")
        response = None
        retry = 0
        max_retries = 10

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")
            except HttpError as e:
                if e.resp.status == 401:
                    logger.warning("Received 401 during chunk upload. Refreshing OAuth credentials...")
                    self.force_refresh_or_reauth()
                    retry += 1
                    if retry > max_retries:
                        raise
                    time.sleep(1)
                    continue
                elif e.resp.status == 403:
                    content_str = e.content.decode("utf-8", errors="ignore")
                    if "quotaExceeded" in content_str:
                        logger.error("Daily YouTube API quota exceeded.")
                        raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
                    raise
                elif e.resp.status in [500, 502, 503, 504]:
                    retry += 1
                    if retry > max_retries:
                        raise
                    sleep_time = (2 ** retry) + random.random()
                    logger.warning(f"Server error {e.resp.status}. Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    raise
            except Exception as e:
                if "invalid_grant" in str(e).lower():
                    logger.warning("Detected invalid_grant during upload chunk. Refreshing credentials...")
                    self.force_refresh_or_reauth()
                    retry += 1
                    if retry > max_retries:
                        raise
                    continue
                retry += 1
                if retry > max_retries:
                    raise
                sleep_time = (2 ** retry) + random.random()
                logger.warning(f"Network error: {e}. Retrying chunk in {sleep_time:.1f}s...")
                time.sleep(sleep_time)

        video_id = response.get("id")
        logger.info(f"Upload completed successfully! Video ID: {video_id}")
        return video_id

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """
        Uploads and sets a custom thumbnail for the video.
        Note: Requires phone-verified YouTube channel.
        """
        try:
            logger.info(f"Setting custom thumbnail for video {video_id}...")
            media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")

            def call():
                return self.get_service().thumbnails().set(
                    videoId=video_id,
                    media_body=media
                ).execute()

            self.execute_api_call(call)
            logger.info("Custom thumbnail successfully set.")
            return True
        except HttpError as e:
            content = e.content.decode("utf-8", errors="ignore")
            if "channelNotEligible" in content or "forbidden" in content:
                logger.warning(
                    "Channel is not eligible for custom thumbnails (requires verified phone number on YouTube). "
                    "Skipping custom thumbnail setting."
                )
                return False
            elif "quotaExceeded" in content:
                raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
            else:
                logger.warning(f"Could not set custom thumbnail: {e}")
                return False
        except Exception as e:
            logger.warning(f"Failed to set custom thumbnail: {e}")
            return False

    def get_or_create_playlist(
        self,
        playlist_title: str,
        description: str = "",
        privacy_status: str = DEFAULT_PRIVACY
    ) -> str:
        """
        Finds an existing playlist by title (checking cache first, then API),
        or creates a new playlist if it doesn't exist.
        """
        cached_id = db.get_cached_playlist_id(playlist_title)
        if cached_id:
            logger.info(f"Using cached playlist ID: '{cached_id}' for '{playlist_title}'")
            return cached_id

        logger.info(f"Searching YouTube for playlist: '{playlist_title}'...")

        page_token = None
        while True:
            def list_call():
                return self.get_service().playlists().list(
                    part="id,snippet",
                    mine=True,
                    maxResults=50,
                    pageToken=page_token
                ).execute()

            response = self.execute_api_call(list_call)

            for item in response.get("items", []):
                title = item["snippet"]["title"].strip()
                if title.lower() == playlist_title.strip().lower():
                    playlist_id = item["id"]
                    logger.info(f"Found existing playlist '{playlist_title}' with ID: {playlist_id}")
                    db.cache_playlist_id(playlist_title, playlist_id)
                    return playlist_id

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        # Playlist not found -> create new playlist
        logger.info(f"Playlist '{playlist_title}' not found. Creating new playlist...")
        body = {
            "snippet": {
                "title": playlist_title,
                "description": description or f"Playlist for {playlist_title}"
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }

        def insert_call():
            return self.get_service().playlists().insert(
                part="snippet,status",
                body=body
            ).execute()

        res = self.execute_api_call(insert_call)
        playlist_id = res["id"]
        logger.info(f"Created new playlist '{playlist_title}' with ID: {playlist_id}")
        db.cache_playlist_id(playlist_title, playlist_id)
        return playlist_id

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> None:
        """Adds a video into a specified playlist."""
        logger.info(f"Adding video {video_id} to playlist {playlist_id}...")
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }

        def add_call():
            return self.get_service().playlistItems().insert(
                part="snippet",
                body=body
            ).execute()

        try:
            self.execute_api_call(add_call)
            logger.info(f"Successfully added video {video_id} to playlist {playlist_id}.")
        except HttpError as e:
            if "quotaExceeded" in str(e):
                raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
            logger.warning(f"Could not add video to playlist: {e}")
