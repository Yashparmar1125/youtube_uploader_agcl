import os
import time
import random
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

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

    def authenticate(self) -> Resource:
        """
        Authenticates with YouTube API using OAuth 2.0.
        Loads existing token from token.json or initiates browser flow.
        """
        creds = None
        if TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), YOUTUBE_SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load existing token from {TOKEN_FILE}: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired YouTube OAuth access token...")
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}. Initiating fresh login.")
                    creds = None

            if not creds:
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
                creds = flow.run_local_server(port=0)

            # Persist the credentials for subsequent runs
            with open(TOKEN_FILE, "w", encoding="utf-8") as token_out:
                token_out.write(creds.to_json())
            logger.info("Saved authorized token to token.json")

        self.service = build("youtube", "v3", credentials=creds)
        return self.service

    def get_service(self) -> Resource:
        if not self.service:
            self.authenticate()
        return self.service

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
        Returns the uploaded YouTube Video ID.
        """
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
                if e.resp.status in [403]:
                    content_str = e.content.decode("utf-8", errors="ignore")
                    if "quotaExceeded" in content_str:
                        logger.error("Daily YouTube API quota exceeded.")
                        raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
                if e.resp.status in [500, 502, 503, 504]:
                    retry += 1
                    if retry > max_retries:
                        raise
                    sleep_time = (2 ** retry) + random.random()
                    logger.warning(f"Server error {e.resp.status}. Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    raise
            except Exception as e:
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
        youtube = self.get_service()
        try:
            logger.info(f"Setting custom thumbnail for video {video_id}...")
            media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=media
            ).execute()
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
        # Check local DB cache first to avoid using API quota
        cached_id = db.get_cached_playlist_id(playlist_title)
        if cached_id:
            logger.info(f"Using cached playlist ID: '{cached_id}' for '{playlist_title}'")
            return cached_id

        youtube = self.get_service()
        logger.info(f"Searching YouTube for playlist: '{playlist_title}'...")

        # Search existing playlists for the authenticated channel
        page_token = None
        while True:
            try:
                response = youtube.playlists().list(
                    part="id,snippet",
                    mine=True,
                    maxResults=50,
                    pageToken=page_token
                ).execute()

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
            except HttpError as e:
                if "quotaExceeded" in str(e):
                    raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
                raise

        # Playlist not found -> create new playlist
        logger.info(f"Playlist '{playlist_title}' not found. Creating new playlist...")
        try:
            body = {
                "snippet": {
                    "title": playlist_title,
                    "description": description or f"Playlist for {playlist_title}"
                },
                "status": {
                    "privacyStatus": privacy_status
                }
            }
            res = youtube.playlists().insert(
                part="snippet,status",
                body=body
            ).execute()
            playlist_id = res["id"]
            logger.info(f"Created new playlist '{playlist_title}' with ID: {playlist_id}")
            db.cache_playlist_id(playlist_title, playlist_id)
            return playlist_id
        except HttpError as e:
            if "quotaExceeded" in str(e):
                raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
            raise

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> None:
        """Adds a video into a specified playlist."""
        youtube = self.get_service()
        logger.info(f"Adding video {video_id} to playlist {playlist_id}...")
        try:
            body = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
            youtube.playlistItems().insert(
                part="snippet",
                body=body
            ).execute()
            logger.info(f"Successfully added video {video_id} to playlist {playlist_id}.")
        except HttpError as e:
            if "quotaExceeded" in str(e):
                raise YouTubeQuotaExceededError("YouTube API daily quota limit exceeded.")
            logger.warning(f"Could not add video to playlist: {e}")
