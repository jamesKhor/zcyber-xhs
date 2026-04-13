"""Analytics module — poll metrics, detect shadowban, weight archetypes.

Polls xiaohongshu-mcp for post metrics at +24h and +7d.
Detects shadowban when views crater across consecutive posts.
Feeds performance data back into scheduling weights.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Optional

import httpx

from .config import Config
from .db import Database
from .models import PostStatus

logger = logging.getLogger("zcyber.analytics")

# Shadowban thresholds
SHADOWBAN_VIEW_THRESHOLD = 100  # Views below this at 24h = suspiciously low
SHADOWBAN_CONSECUTIVE = 3       # N consecutive low-view posts = likely shadowban
HEALTHY_VIEW_THRESHOLD = 200    # Views above this = healthy distribution


class Analytics:
    """Poll metrics and analyze post performance."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.mcp_url = config.publishing.get("xhs_mcp_url", "http://localhost:18060")

    # ── Metric Polling ───────────────────────────────────

    def poll_all_published(self) -> int:
        """Poll metrics for all published posts that need updating.

        Returns count of posts updated.
        """
        posts = self.db.list_posts(status=PostStatus.PUBLISHED, limit=50)
        updated = 0

        for post in posts:
            if not post.published_at:
                continue

            published_at = datetime.fromisoformat(str(post.published_at))
            hours_since = int(
                (datetime.now(UTC) - published_at.replace(tzinfo=UTC)).total_seconds() / 3600
            )

            # Poll at +24h and +7d (168h)
            existing = self.db.get_latest_metrics(post.id)
            last_hours = existing.get("hours_since_publish", 0) if existing else 0

            should_poll = (
                (hours_since >= 24 and last_hours < 24)
                or (hours_since >= 168 and last_hours < 168)
                or (not existing and hours_since >= 12)
            )

            if should_poll:
                metrics = self._fetch_metrics(post.published_url)
                if metrics:
                    self.db.insert_metrics(
                        post_id=post.id,
                        views=metrics.get("views", 0),
                        likes=metrics.get("likes", 0),
                        comments=metrics.get("comments", 0),
                        shares=metrics.get("shares", 0),
                        saves=metrics.get("saves", 0),
                        hours_since=hours_since,
                    )
                    updated += 1
                    logger.info(
                        f"Post #{post.id} at +{hours_since}h: "
                        f"{metrics.get('views', 0)} views"
                    )

        return updated

    def _fetch_metrics(self, published_url: Optional[str]) -> Optional[dict]:
        """Fetch metrics from xiaohongshu-mcp for a specific post."""
        if not published_url:
            return None

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{self.mcp_url.rstrip('/')}/metrics",
                    params={"url": published_url},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch metrics for {published_url}: {e}")
            return None

    # ── Shadowban Detection ──────────────────────────────

    def check_shadowban(self) -> ShadowbanStatus:
        """Check if the account appears to be shadowbanned.

        Logic: if the last N consecutive published posts all have
        views < threshold at 24h+, flag as likely shadowban.
        """
        recent = self.db.get_recent_published_metrics(limit=SHADOWBAN_CONSECUTIVE + 2)

        if len(recent) < SHADOWBAN_CONSECUTIVE:
            return ShadowbanStatus(
                is_shadowbanned=False,
                confidence="insufficient_data",
                message=f"Only {len(recent)} posts with metrics, need {SHADOWBAN_CONSECUTIVE}",
            )

        # Check consecutive low-view posts
        consecutive_low = 0
        for post_data in recent:
            views = post_data.get("views", 0) or 0
            hours = post_data.get("hours_since_publish", 0) or 0

            if hours >= 24 and views < SHADOWBAN_VIEW_THRESHOLD:
                consecutive_low += 1
            else:
                break

        if consecutive_low >= SHADOWBAN_CONSECUTIVE:
            self.db.log_health_event(
                "shadowban_detected",
                f"{consecutive_low} consecutive posts with <{SHADOWBAN_VIEW_THRESHOLD} "
                f"views at 24h+",
                severity="critical",
            )
            return ShadowbanStatus(
                is_shadowbanned=True,
                confidence="high",
                consecutive_low=consecutive_low,
                message=(
                    f"LIKELY SHADOWBAN: {consecutive_low} consecutive posts with "
                    f"<{SHADOWBAN_VIEW_THRESHOLD} views. Auto-pausing pipeline."
                ),
            )

        # Check if views are trending down
        if len(recent) >= 3:
            views_list = [
                (r.get("views", 0) or 0)
                for r in recent[:5]
                if (r.get("hours_since_publish", 0) or 0) >= 24
            ]
            if len(views_list) >= 3 and all(
                views_list[i] <= views_list[i + 1] * 0.5
                for i in range(min(2, len(views_list) - 1))
            ):
                return ShadowbanStatus(
                    is_shadowbanned=False,
                    confidence="warning",
                    message="Views declining rapidly (50%+ drop). Monitor closely.",
                )

        return ShadowbanStatus(
            is_shadowbanned=False,
            confidence="healthy",
            message="Post distribution appears normal.",
        )

    def auto_pause_if_shadowbanned(self) -> bool:
        """Check shadowban and pause the pipeline if detected.

        Returns True if paused.
        """
        status = self.check_shadowban()

        if status.is_shadowbanned:
            logger.critical(status.message)
            self._send_alert(status.message)
            return True

        if status.confidence == "warning":
            logger.warning(status.message)
            self._send_alert(status.message)

        return False

    # ── Archetype Performance ────────────────────────────

    def get_archetype_performance(self) -> dict[str, dict]:
        """Get average performance metrics per archetype."""
        rows = self.db.conn.execute(
            """SELECT p.archetype,
                      COUNT(DISTINCT p.id) as post_count,
                      AVG(m.views) as avg_views,
                      AVG(m.likes) as avg_likes,
                      AVG(m.comments) as avg_comments,
                      AVG(m.saves) as avg_saves,
                      AVG(m.shares) as avg_shares
               FROM posts p
               JOIN post_metrics m ON p.id = m.post_id
               WHERE p.status = 'published'
               AND m.hours_since_publish >= 24
               GROUP BY p.archetype
               ORDER BY avg_views DESC"""
        ).fetchall()

        return {
            row["archetype"]: {
                "post_count": row["post_count"],
                "avg_views": round(row["avg_views"] or 0),
                "avg_likes": round(row["avg_likes"] or 0),
                "avg_comments": round(row["avg_comments"] or 0),
                "avg_saves": round(row["avg_saves"] or 0),
                "avg_shares": round(row["avg_shares"] or 0),
                "engagement_rate": _calc_engagement_rate(row),
            }
            for row in rows
        }

    def get_best_archetype(self) -> Optional[str]:
        """Get the best-performing archetype by engagement rate."""
        perf = self.get_archetype_performance()
        if not perf:
            return None
        return max(perf, key=lambda k: perf[k]["engagement_rate"])

    # ── Alerts ───────────────────────────────────────────

    def _send_alert(self, message: str) -> None:
        """Send alert via Telegram if configured."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return

        try:
            import asyncio

            from telegram import Bot

            async def _send():
                bot = Bot(token=token)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🚨 *ZCYBER\\-XHS ALERT*\n\n{_escape_md(message)}",
                    parse_mode="MarkdownV2",
                )

            asyncio.run(_send())
        except Exception as e:
            logger.error(f"Alert send failed: {e}")


class ShadowbanStatus:
    """Result of shadowban detection."""

    def __init__(
        self,
        is_shadowbanned: bool = False,
        confidence: str = "unknown",
        consecutive_low: int = 0,
        message: str = "",
    ):
        self.is_shadowbanned = is_shadowbanned
        self.confidence = confidence
        self.consecutive_low = consecutive_low
        self.message = message


def _calc_engagement_rate(row: dict) -> float:
    """Calculate engagement rate: (likes + comments + saves) / views."""
    views = row["avg_views"] or 0
    if views == 0:
        return 0.0
    engagement = (row["avg_likes"] or 0) + (row["avg_comments"] or 0) + (row["avg_saves"] or 0)
    return round(engagement / views * 100, 2)


def _escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars for Telegram."""
    for ch in [
        "_", "*", "[", "]", "(", ")", "~", "`",
        ">", "#", "+", "-", "=", "|", "{", "}", ".", "!",
    ]:
        text = text.replace(ch, f"\\{ch}")
    return text
