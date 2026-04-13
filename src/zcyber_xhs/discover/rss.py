"""RSS feed discovery — pulls latest articles from zcybernews for news_hook."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from ..db import Database
from ..models import TopicEntry

# Default: zcybernews Chinese feed
DEFAULT_FEED_URL = "https://www.zcybernews.com/api/feed?locale=zh"


class RSSDiscovery:
    """Fetch news from zcybernews RSS feed for news_hook archetype."""

    def __init__(self, db: Database, feed_url: str = DEFAULT_FEED_URL):
        self.db = db
        self.feed_url = feed_url

    def pick_topic(self) -> Optional[TopicEntry]:
        """Fetch the RSS feed and return the first unused article as a topic."""
        articles = self._fetch_feed()
        if not articles:
            return None

        for article in articles:
            slug = self._slugify(article["title"])
            if not self.db.is_topic_used("news_hook", slug):
                self.db.mark_topic_used("news_hook", slug)
                return TopicEntry(
                    slug=slug,
                    problem=article["title"],
                    news_title=article["title"],
                    news_excerpt=article.get("description", ""),
                    news_url=article.get("link", ""),
                    news_date=article.get("pubDate", ""),
                    news_category=article.get("category", "cybersecurity"),
                    category="news",
                )

        return None

    def _fetch_feed(self) -> list[dict]:
        """Fetch and parse the RSS feed, returning a list of article dicts."""
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(self.feed_url)
                resp.raise_for_status()
        except httpx.HTTPError:
            return []

        return self._parse_rss(resp.text)

    @staticmethod
    def _parse_rss(xml_text: str) -> list[dict]:
        """Parse RSS XML into a list of article dicts."""
        articles = []
        try:
            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            if channel is None:
                return []

            for item in channel.findall("item"):
                article = {
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "description": (item.findtext("description") or "").strip(),
                    "pubDate": (item.findtext("pubDate") or "").strip(),
                    "category": (item.findtext("category") or "").strip(),
                }
                if article["title"]:
                    articles.append(article)
        except ET.ParseError:
            return []

        return articles

    @staticmethod
    def _slugify(title: str) -> str:
        """Create a URL-safe slug from a title."""
        import hashlib
        import re

        # Use hash for CJK titles since they don't slugify well
        safe = re.sub(r"[^\w\s-]", "", title.lower())
        safe = re.sub(r"[\s_]+", "-", safe).strip("-")
        if not safe or len(safe) < 3:
            safe = hashlib.md5(title.encode()).hexdigest()[:12]
        return safe[:60]
