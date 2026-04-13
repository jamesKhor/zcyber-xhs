"""Publisher — sends approved posts to xiaohongshu-mcp."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

import httpx

from .config import Config
from .db import Database
from .models import PostRecord, PostStatus


class Publisher:
    """HTTP client for xiaohongshu-mcp to publish posts to XHS."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.base_url = config.publishing.get("xhs_mcp_url", "http://localhost:18060")
        self.retry_attempts = config.publishing.get("retry_attempts", 3)
        self.jitter_minutes = config.publishing.get("jitter_minutes", 20)

    def publish(self, post: PostRecord) -> Optional[str]:
        """Publish a post to XHS via xiaohongshu-mcp.

        Returns the published URL on success, None on failure.
        """
        # Apply jitter delay
        jitter = random.randint(0, self.jitter_minutes * 60)
        if jitter > 0:
            time.sleep(jitter)

        # Build the request payload for xiaohongshu-mcp
        payload = self._build_payload(post)

        for attempt in range(1, self.retry_attempts + 1):
            try:
                url = self._resolve_publish_url()
                with httpx.Client(timeout=60) as client:
                    response = client.post(url, json=payload)
                    response.raise_for_status()
                    result = response.json()

                published_url = result.get("url", result.get("note_url", ""))
                self.db.update_post_status(
                    post.id,
                    PostStatus.PUBLISHED,
                    published_url=published_url,
                )
                return published_url

            except (httpx.HTTPError, Exception) as e:
                if attempt < self.retry_attempts:
                    backoff = 2**attempt * 30  # 60s, 120s, 240s
                    time.sleep(backoff)
                else:
                    self.db.update_post_status(post.id, PostStatus.FAILED)
                    raise RuntimeError(
                        f"Failed to publish post {post.id} after"
                        f" {self.retry_attempts} attempts: {e}"
                    ) from e

        return None

    def _build_payload(self, post: PostRecord) -> dict:
        """Build the xiaohongshu-mcp API payload."""
        payload = {
            "title": post.title,
            "content": post.body,
            "tags": post.tags,
        }

        # Attach image(s) — supports single path or JSON array of paths
        if post.image_path:
            image_paths = self._resolve_image_paths(post.image_path)
            if image_paths:
                payload["image_paths"] = image_paths

        return payload

    @staticmethod
    def _resolve_image_paths(image_path_str: str) -> list[str]:
        """Parse image path(s) — handles both single path and JSON array."""
        import json

        if image_path_str.startswith("["):
            try:
                paths = json.loads(image_path_str)
                return [p for p in paths if Path(p).exists()]
            except json.JSONDecodeError:
                pass

        if Path(image_path_str).exists():
            return [image_path_str]

        return []

    def _resolve_publish_url(self) -> str:
        """Resolve the xiaohongshu-mcp publish endpoint."""
        base = self.base_url.rstrip("/")
        return f"{base}/publish"

    def health_check(self) -> bool:
        """Check if xiaohongshu-mcp is reachable."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self.base_url.rstrip('/')}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
