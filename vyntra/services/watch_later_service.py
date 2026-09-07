"""
Persistent Watch Later / Favorites Service for Vyntra using SQLite.
"""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from typing import List, Optional

from vyntra.config import config_manager
from vyntra.models import SearchResult
from vyntra.utils.logger import logger


class WatchLaterItem:
    """Represents a saved video in Watch Later with metadata and timestamp."""

    def __init__(self, result: SearchResult, added_at: str):
        self.result = result
        self.added_at = added_at


class WatchLaterService:
    """Manages persistent Watch Later / Favorites storage in a local SQLite database."""

    def __init__(self, db_path: Optional[Path] = None):
        self._lock = threading.Lock()
        if db_path is None:
            config_dir = Path.home() / ".vyntra"
            config_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = config_dir / "library.db"
        else:
            self._db_path = db_path

        self._init_db()

    @contextmanager
    def _db_connection(self):
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initializes the watch_later table if it does not already exist."""
        with self._lock:
            with self._db_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS watch_later (
                        video_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        channel TEXT,
                        duration_seconds INTEGER DEFAULT 0,
                        duration_formatted TEXT,
                        thumbnail_url TEXT,
                        url TEXT,
                        views_formatted TEXT,
                        added_at TEXT NOT NULL
                    )
                """)
                conn.commit()

    def add(self, result: SearchResult) -> bool:
        """
        Adds a video to Watch Later.
        Returns True if added successfully, False if already present (duplicate).
        """
        with self._lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.execute(
                        "SELECT video_id FROM watch_later WHERE video_id = ?",
                        (result.video_id,),
                    )
                    if cursor.fetchone() is not None:
                        return False

                    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
                    conn.execute(
                        """
                        INSERT INTO watch_later (
                            video_id, title, channel, duration_seconds,
                            duration_formatted, thumbnail_url, url,
                            views_formatted, added_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result.video_id,
                            result.title,
                            result.channel,
                            result.duration_seconds or 0,
                            result.duration_formatted or "00:00",
                            result.thumbnail_url or "",
                            result.url or f"https://www.youtube.com/watch?v={result.video_id}",
                            result.views_formatted or "",
                            now_iso,
                        ),
                    )
                    conn.commit()
                    logger.info("Saved video '%s' (%s) to Watch Later.", result.display_title, result.video_id)
                    return True
            except Exception as e:
                logger.error("Error saving video to Watch Later: %s", e)
                return False

    def remove(self, video_id: str) -> bool:
        """Removes a video from Watch Later by video_id."""
        with self._lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.execute("DELETE FROM watch_later WHERE video_id = ?", (video_id,))
                    conn.commit()
                    removed = cursor.rowcount > 0
                    if removed:
                        logger.info("Removed video %s from Watch Later.", video_id)
                    return removed
            except Exception as e:
                logger.error("Error removing video %s from Watch Later: %s", video_id, e)
                return False

    def is_saved(self, video_id: str) -> bool:
        """Checks if a video is already saved in Watch Later."""
        with self._lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.execute("SELECT 1 FROM watch_later WHERE video_id = ?", (video_id,))
                    return cursor.fetchone() is not None
            except Exception as e:
                logger.debug("Error checking is_saved for %s: %s", video_id, e)
                return False

    def get_all(self) -> List[WatchLaterItem]:
        """Returns all saved items ordered by most recently added."""
        with self._lock:
            items: List[WatchLaterItem] = []
            try:
                with self._db_connection() as conn:
                    cursor = conn.execute(
                        """
                        SELECT video_id, title, channel, duration_seconds,
                               duration_formatted, thumbnail_url, url,
                               views_formatted, added_at
                        FROM watch_later
                        ORDER BY rowid DESC
                        """
                    )
                    for row in cursor.fetchall():
                        res = SearchResult(
                            video_id=row["video_id"],
                            title=row["title"],
                            channel=row["channel"] or "Unknown Channel",
                            duration_seconds=row["duration_seconds"],
                            duration_formatted=row["duration_formatted"],
                            thumbnail_url=row["thumbnail_url"],
                            url=row["url"],
                            views_formatted=row["views_formatted"],
                        )
                        items.append(WatchLaterItem(result=res, added_at=row["added_at"]))
            except Exception as e:
                logger.error("Error fetching Watch Later items: %s", e)
            return items

    def count(self) -> int:
        """Returns total number of saved videos."""
        with self._lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM watch_later")
                    row = cursor.fetchone()
                    return row[0] if row else 0
            except Exception as e:
                logger.debug("Error counting Watch Later items: %s", e)
                return 0


# Global singleton instance
watch_later_service = WatchLaterService()
