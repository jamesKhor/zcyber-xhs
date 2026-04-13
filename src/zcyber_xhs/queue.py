"""Draft queue management — approve, reject, and list posts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Optional

from .config import Config
from .db import Database
from .models import PostDraft, PostRecord, PostStatus


class DraftQueue:
    """Manage the post draft queue backed by SQLite."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db

    def enqueue(
        self,
        draft: PostDraft,
        topic_slug: str,
        image_path: Optional[str] = None,
        payload_json: Optional[str] = None,
    ) -> int:
        """Add a generated draft to the queue. Returns the post ID."""
        record = PostRecord(
            archetype=draft.archetype.value,
            topic_slug=topic_slug,
            title=draft.title,
            body=draft.body,
            tags=draft.tags,
            image_path=image_path,
            payload_json=payload_json or json.dumps(
                draft.model_dump(), ensure_ascii=False, indent=2
            ),
            status=PostStatus.DRAFT,
        )
        return self.db.insert_post(record)

    def approve(self, post_id: int) -> bool:
        """Mark a draft as approved for publishing."""
        post = self.db.get_post(post_id)
        if not post or post.status != PostStatus.DRAFT:
            return False
        self.db.update_post_status(post_id, PostStatus.APPROVED)
        return True

    def reject(self, post_id: int) -> bool:
        """Mark a draft as rejected."""
        post = self.db.get_post(post_id)
        if not post or post.status != PostStatus.DRAFT:
            return False
        self.db.update_post_status(post_id, PostStatus.REJECTED)
        return True

    def list_drafts(self, limit: int = 20) -> list[PostRecord]:
        return self.db.list_posts(status=PostStatus.DRAFT, limit=limit)

    def list_approved(self, limit: int = 20) -> list[PostRecord]:
        return self.db.list_posts(status=PostStatus.APPROVED, limit=limit)

    def next_publishable(self) -> Optional[PostRecord]:
        """Get the next approved post ready for publishing.

        Respects rate limits: max_per_day and min_hours_between.
        """
        pub_config = self.config.publishing

        # Check daily limit
        today_count = self.db.count_published_today()
        max_per_day = pub_config.get("max_per_day", 2)
        if today_count >= max_per_day:
            return None

        # Check minimum interval between posts
        min_hours = pub_config.get("min_hours_between", 4)
        recent = self.db.list_posts(status=PostStatus.PUBLISHED, limit=1)
        if recent and recent[0].published_at:
            last_published = datetime.fromisoformat(str(recent[0].published_at))
            if datetime.now(UTC) - last_published < timedelta(hours=min_hours):
                return None

        approved = self.db.list_posts(status=PostStatus.APPROVED, limit=1)
        return approved[0] if approved else None
