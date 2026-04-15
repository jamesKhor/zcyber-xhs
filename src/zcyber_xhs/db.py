"""SQLite database — schema, migrations, and helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from .models import PostRecord, PostStatus

DB_NAME = "zcyber_xhs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archetype TEXT NOT NULL,
    topic_slug TEXT NOT NULL,
    title TEXT,
    body TEXT,
    tags TEXT,
    image_path TEXT,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    scheduled_for DATETIME,
    published_url TEXT,
    published_at DATETIME,
    metrics_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topics_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archetype TEXT NOT NULL,
    topic_slug TEXT NOT NULL,
    used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(archetype, topic_slug)
);

CREATE TABLE IF NOT EXISTS post_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    polled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    hours_since_publish INTEGER DEFAULT 0,
    FOREIGN KEY (post_id) REFERENCES posts(id)
);

CREATE TABLE IF NOT EXISTS pipeline_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT,
    severity TEXT DEFAULT 'info',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_archetype ON posts(archetype);
CREATE INDEX IF NOT EXISTS idx_topics_history_lookup ON topics_history(archetype, topic_slug);
CREATE INDEX IF NOT EXISTS idx_post_metrics_post ON post_metrics(post_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_health_type ON pipeline_health(event_type);
"""


class Database:
    def __init__(
        self, db_path: str | Path | None = None, *, cross_thread: bool = False
    ):
        if db_path is None:
            db_path = Path.cwd() / DB_NAME
        self.db_path = Path(db_path)
        self._cross_thread = cross_thread
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=not self._cross_thread,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init(self) -> None:
        """Create tables if they don't exist."""
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Posts ──────────────────────────────────────────────

    def insert_post(self, post: PostRecord) -> int:
        """Insert a new post and return its ID."""
        cur = self.conn.execute(
            """INSERT INTO posts
               (archetype, topic_slug, title, body, tags, image_path,
                payload_json, status, scheduled_for)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post.archetype,
                post.topic_slug,
                post.title,
                post.body,
                json.dumps(post.tags, ensure_ascii=False),
                post.image_path,
                post.payload_json,
                post.status.value,
                post.scheduled_for.isoformat() if post.scheduled_for else None,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_post(self, post_id: int) -> Optional[PostRecord]:
        row = self.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            return None
        return self._row_to_post(row)

    def list_posts(
        self, status: Optional[PostStatus] = None, limit: int = 50
    ) -> list[PostRecord]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def update_post_status(
        self,
        post_id: int,
        status: PostStatus,
        published_url: Optional[str] = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        if status == PostStatus.PUBLISHED and published_url:
            self.conn.execute(
                "UPDATE posts SET status=?, published_url=?, published_at=?,"
                " updated_at=? WHERE id=?",
                (status.value, published_url, now, now, post_id),
            )
        else:
            self.conn.execute(
                "UPDATE posts SET status=?, updated_at=? WHERE id=?",
                (status.value, now, post_id),
            )
        self.conn.commit()

    def delete_post(self, post_id: int) -> bool:
        """Hard-delete a post. Returns True if a row was deleted."""
        cur = self.conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def update_post_image(self, post_id: int, image_path: str) -> None:
        """Set or update the image_path for an existing post."""
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "UPDATE posts SET image_path=?, updated_at=? WHERE id=?",
            (image_path, now, post_id),
        )
        self.conn.commit()

    def count_published_today(self) -> int:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT COUNT(*) FROM posts WHERE status='published' AND date(published_at)=?",
            (today,),
        ).fetchone()
        return row[0]

    # ── Topic History ─────────────────────────────────────

    def is_topic_used(self, archetype: str, topic_slug: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM topics_history WHERE archetype=? AND topic_slug=?",
            (archetype, topic_slug),
        ).fetchone()
        return row is not None

    def mark_topic_used(self, archetype: str, topic_slug: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO topics_history (archetype, topic_slug) VALUES (?, ?)",
            (archetype, topic_slug),
        )
        self.conn.commit()

    # ── Metrics ───────────────────────────────────────────

    def insert_metrics(
        self,
        post_id: int,
        views: int = 0,
        likes: int = 0,
        comments: int = 0,
        shares: int = 0,
        saves: int = 0,
        hours_since: int = 0,
    ) -> None:
        self.conn.execute(
            """INSERT INTO post_metrics
               (post_id, views, likes, comments, shares, saves, hours_since_publish)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (post_id, views, likes, comments, shares, saves, hours_since),
        )
        self.conn.commit()

    def get_latest_metrics(self, post_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM post_metrics WHERE post_id=? ORDER BY id DESC LIMIT 1",
            (post_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_recent_published_metrics(self, limit: int = 10) -> list[dict]:
        """Get latest metrics for recently published posts."""
        rows = self.conn.execute(
            """SELECT p.id, p.title, p.archetype, p.published_at,
                      m.views, m.likes, m.comments, m.shares, m.saves,
                      m.hours_since_publish
               FROM posts p
               LEFT JOIN post_metrics m ON p.id = m.post_id
               WHERE p.status = 'published'
               AND m.id = (
                   SELECT MAX(m2.id) FROM post_metrics m2 WHERE m2.post_id = p.id
               )
               ORDER BY p.published_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Pipeline Health ──────────────────────────────────

    def log_health_event(
        self, event_type: str, message: str, severity: str = "info"
    ) -> None:
        self.conn.execute(
            "INSERT INTO pipeline_health (event_type, message, severity) VALUES (?, ?, ?)",
            (event_type, message, severity),
        )
        self.conn.commit()

    def get_health_events(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM pipeline_health ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> PostRecord:
        tags_raw = row["tags"]
        tags = json.loads(tags_raw) if tags_raw else []
        return PostRecord(
            id=row["id"],
            archetype=row["archetype"],
            topic_slug=row["topic_slug"],
            title=row["title"],
            body=row["body"],
            tags=tags,
            image_path=row["image_path"],
            payload_json=row["payload_json"],
            status=PostStatus(row["status"]),
            published_url=row["published_url"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
