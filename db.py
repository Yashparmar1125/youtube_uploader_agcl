import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Initializes the SQLite database schema and migrates old schema to folder-scoped uniqueness."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if uploads table exists and whether it needs migration
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='uploads'")
        row = cursor.fetchone()
        if row and ("file_hash TEXT UNIQUE" in row["sql"] or "file_path TEXT UNIQUE" in row["sql"]):
            cursor.execute("ALTER TABLE uploads RENAME TO uploads_old")
            cursor.execute("""
                CREATE TABLE uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    folder_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    youtube_video_id TEXT,
                    youtube_playlist_id TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(folder_name, file_hash)
                )
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO uploads (
                    id, file_path, file_hash, file_size, folder_name, title,
                    youtube_video_id, youtube_playlist_id, status, error_message, created_at, updated_at
                )
                SELECT id, file_path, file_hash, file_size, folder_name, title,
                       youtube_video_id, youtube_playlist_id, status, error_message, created_at, updated_at
                FROM uploads_old
            """)
            cursor.execute("DROP TABLE uploads_old")
            conn.commit()
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    folder_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    youtube_video_id TEXT,
                    youtube_playlist_id TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(folder_name, file_hash)
                )
            """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlists_cache (
                title TEXT PRIMARY KEY,
                playlist_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def compute_file_hash(file_path: Path, chunk_size: int = 65536) -> str:
    """Computes SHA-256 hash of a file using chunks to avoid high memory consumption."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()

def is_file_processed(file_hash: str, folder_name: str) -> bool:
    """Checks if an audio file has already been successfully uploaded for a specific folder/playlist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM uploads WHERE file_hash = ? AND folder_name = ?",
            (file_hash, folder_name)
        )
        row = cursor.fetchone()
        return bool(row and row["status"] == "COMPLETED")

def get_file_record(file_hash: str, folder_name: str) -> Optional[Dict[str, Any]]:
    """Retrieves an upload record by file hash and folder name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM uploads WHERE file_hash = ? AND folder_name = ?",
            (file_hash, folder_name)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

def register_file(file_path: Path, file_hash: str, file_size: int, folder_name: str, title: str) -> None:
    """Registers a new audio file for a specific folder/playlist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO uploads (file_path, file_hash, file_size, folder_name, title, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            ON CONFLICT(folder_name, file_hash) DO UPDATE SET
                file_path = excluded.file_path,
                updated_at = CURRENT_TIMESTAMP
        """, (str(file_path), file_hash, file_size, folder_name, title))
        conn.commit()

def update_status(
    file_hash: str,
    folder_name: str,
    status: str,
    youtube_video_id: Optional[str] = None,
    youtube_playlist_id: Optional[str] = None,
    error_message: Optional[str] = None
) -> None:
    """Updates the status and YouTube details of a file in a specific folder/playlist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE uploads SET
                status = ?,
                youtube_video_id = COALESCE(?, youtube_video_id),
                youtube_playlist_id = COALESCE(?, youtube_playlist_id),
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE file_hash = ? AND folder_name = ?
        """, (status, youtube_video_id, youtube_playlist_id, error_message, file_hash, folder_name))
        conn.commit()

def get_cached_playlist_id(playlist_title: str) -> Optional[str]:
    """Retrieves a cached YouTube playlist ID by its title."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT playlist_id FROM playlists_cache WHERE title = ?", (playlist_title,))
        row = cursor.fetchone()
        return row["playlist_id"] if row else None

def cache_playlist_id(playlist_title: str, playlist_id: str) -> None:
    """Caches a YouTube playlist ID for future reference to save API quota."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO playlists_cache (title, playlist_id)
            VALUES (?, ?)
            ON CONFLICT(title) DO UPDATE SET
                playlist_id = excluded.playlist_id
        """, (playlist_title, playlist_id))
        conn.commit()

def get_today_upload_count() -> int:
    """Returns the number of videos successfully uploaded today (UTC date)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM uploads
            WHERE status = 'COMPLETED'
            AND DATE(updated_at) = DATE('now')
        """)
        row = cursor.fetchone()
        return row[0] if row else 0
