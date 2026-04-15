"""Publisher — sends approved posts to xiaohongshu-mcp via MCP protocol."""

from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from .config import Config
from .db import Database
from .models import PostRecord, PostStatus


class Publisher:
    """MCP client for xiaohongshu-mcp to publish posts to XHS."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.base_url = config.publishing.get(
            "xhs_mcp_url", "http://localhost:18060"
        )
        self.mcp_endpoint = f"{self.base_url.rstrip('/')}/mcp"
        self.retry_attempts = config.publishing.get("retry_attempts", 3)
        self.jitter_minutes = config.publishing.get("jitter_minutes", 20)
        self._session_id: Optional[str] = None

    def _init_session(self, client: httpx.Client) -> None:
        """Initialize MCP session handshake."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # Step 1: initialize
        resp = client.post(
            self.mcp_endpoint,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "zcyber-xhs-publisher",
                        "version": "1.0",
                    },
                },
            },
        )
        resp.raise_for_status()
        self._session_id = resp.headers.get("Mcp-Session-Id")

        # Step 2: send initialized notification
        headers["Mcp-Session-Id"] = self._session_id
        client.post(
            self.mcp_endpoint,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )

    def _call_tool(
        self, client: httpx.Client, tool_name: str, arguments: dict
    ) -> dict:
        """Call an MCP tool and return the result."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        resp = client.post(
            self.mcp_endpoint,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
        )
        resp.raise_for_status()
        return resp.json()

    def publish(self, post: PostRecord) -> Optional[str]:
        """Publish a post to XHS via xiaohongshu-mcp.

        Returns the published URL on success, None on failure.
        """
        # Apply jitter delay
        jitter = random.randint(0, self.jitter_minutes * 60)
        if jitter > 0:
            time.sleep(jitter)

        image_paths = self._resolve_image_paths(post.image_path)
        if not image_paths:
            raise RuntimeError(
                f"Post {post.id} has no valid images — XHS requires at least 1"
            )

        # Strip # from tags — MCP adds them automatically
        tags = [t.lstrip("#") for t in (post.tags or [])]

        arguments = {
            "title": post.title[:20] if post.title else "",
            "content": post.body or "",
            "images": image_paths,
            "tags": tags,
            "is_original": True,
            "visibility": "公开可见",
        }

        for attempt in range(1, self.retry_attempts + 1):
            try:
                with httpx.Client(timeout=120) as client:
                    self._init_session(client)
                    result = self._call_tool(
                        client, "publish_content", arguments
                    )

                # Check for MCP error
                if "error" in result:
                    raise RuntimeError(
                        f"MCP error: {result['error'].get('message', result['error'])}"
                    )

                # Extract published URL from result
                content = result.get("result", {})
                published_url = self._extract_url(content)

                self.db.update_post_status(
                    post.id,
                    PostStatus.PUBLISHED,
                    published_url=published_url,
                )
                return published_url

            except Exception as e:
                if attempt < self.retry_attempts:
                    backoff = 2**attempt * 30
                    time.sleep(backoff)
                else:
                    self.db.update_post_status(post.id, PostStatus.FAILED)
                    raise RuntimeError(
                        f"Failed to publish post {post.id} after"
                        f" {self.retry_attempts} attempts: {e}"
                    ) from e

        return None

    @staticmethod
    def _extract_url(content: dict) -> str:
        """Extract published URL from MCP tool result."""
        # The result may contain the URL in various formats
        if isinstance(content, dict):
            for key in ("url", "note_url", "link"):
                if key in content:
                    return content[key]
            # Check nested content array (MCP standard format)
            for item in content.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if "xhslink" in text or "xiaohongshu" in text:
                        return text
        return ""

    @staticmethod
    def _resolve_image_paths(image_path_str: str | None) -> list[str]:
        """Parse image path(s) — handles both single path and JSON array."""
        if not image_path_str:
            return []

        if image_path_str.startswith("["):
            try:
                paths = json.loads(image_path_str)
                return [p for p in paths if Path(p).exists()]
            except json.JSONDecodeError:
                pass

        if Path(image_path_str).exists():
            return [image_path_str]

        return []

    def health_check(self) -> bool:
        """Check if xiaohongshu-mcp is reachable and logged in."""
        try:
            with httpx.Client(timeout=30) as client:
                self._init_session(client)
                result = self._call_tool(
                    client, "check_login_status", {}
                )
                # Check for successful result with login confirmation
                text = str(result.get("result", {}).get("content", ""))
                return "已登录" in text or "error" not in result
        except Exception:
            return False
