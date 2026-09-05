"""
Script to update existing uploaded videos from 'private' to 'public' on YouTube.
"""
import sys
import logging
from googleapiclient.errors import HttpError

import config
import db
from youtube_client import YouTubeClient

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def update_privacy(video_id: str, new_privacy: str = "public"):
    client = YouTubeClient()

    logger.info(f"Setting video {video_id} to '{new_privacy}'...")
    try:
        # Retrieve video snippet and status with auto-refresh retry
        res = client.execute_api_call(
            lambda: client.get_service().videos().list(part="snippet,status", id=video_id).execute()
        )
        items = res.get("items", [])
        if not items:
            logger.warning(f"Video {video_id} not found on YouTube.")
            return False

        item = items[0]
        snippet = item["snippet"]

        update_body = {
            "id": video_id,
            "snippet": {
                "title": snippet["title"],
                "categoryId": snippet["categoryId"]
            },
            "status": {
                "privacyStatus": new_privacy,
                "selfDeclaredMadeForKids": False
            }
        }

        client.execute_api_call(
            lambda: client.get_service().videos().update(
                part="snippet,status",
                body=update_body
            ).execute()
        )
        logger.info(f"Successfully updated video {video_id} to '{new_privacy}'!")
        return True
    except HttpError as e:
        logger.error(f"Failed to update video {video_id}: {e}")
        return False

def publish_all_in_db():
    with db.get_connection() as conn:
        rows = conn.execute("SELECT id, title, youtube_video_id, status FROM uploads WHERE youtube_video_id IS NOT NULL").fetchall()

    if not rows:
        print("No uploaded videos found in database.")
        return

    print(f"Found {len(rows)} uploaded video(s) in database:")
    for r in rows:
        print(f" - [{r['youtube_video_id']}] {r['title']}")

    confirm = input("\nDo you want to change all these videos to 'public' now? (y/n): ").strip().lower()
    if confirm in ["y", "yes"]:
        for r in rows:
            vid = r["youtube_video_id"]
            title = r["title"]
            logger.info(f"Publishing: '{title}' ({vid})")
            update_privacy(vid, "public")
        print("\nAll videos have been set to public!")
    else:
        print("Cancelled.")

if __name__ == "__main__":
    publish_all_in_db()
