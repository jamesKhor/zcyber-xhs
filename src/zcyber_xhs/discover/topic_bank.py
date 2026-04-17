"""Topic discovery from YAML topic banks, with dedup against history.

When a bank is exhausted (all topics used), DynamicTopicGenerator is called
to synthesise a fresh topic via LLM so generation never stalls.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

from ..db import Database
from ..models import TopicEntry

if TYPE_CHECKING:
    from ..generate.llm import LLMClient


class TopicBank:
    """Load topics from YAML banks and pick unused ones.

    Pass an LLMClient to enable dynamic topic generation when the bank
    is exhausted.  Without one the old behaviour (return None) is kept.
    """

    def __init__(self, config_dir: Path, db: Database):
        self.banks_dir = config_dir / "topic_banks"
        self.config_dir = config_dir
        self.db = db

    def pick_topic(
        self, archetype: str, llm: Optional["LLMClient"] = None
    ) -> Optional[TopicEntry]:
        """Pick a random unused topic for the given archetype.

        1. Try the YAML bank first (curated quality, fast).
        2. If the bank is exhausted and an LLM client is provided,
           generate a fresh topic dynamically.
        3. Returns None only if both sources fail.
        """
        results = self.pick_n_topics(archetype, 1)
        if results:
            return results[0]

        # Bank exhausted — fall back to LLM dynamic generation
        if llm is not None:
            from .dynamic_topic import DynamicTopicGenerator

            # Collect recent topic slugs for this archetype to avoid repetition
            recent_posts = self.db.list_posts(limit=8)
            recent_slugs = [
                p.topic_slug
                for p in recent_posts
                if p.archetype == archetype and p.topic_slug
            ]

            gen = DynamicTopicGenerator(llm, self.config_dir)
            topic = gen.generate(archetype, recent_titles=recent_slugs)
            if topic:
                # Mark the dynamic slug as used so it won't be re-used
                self.db.mark_topic_used(archetype, topic.slug)
                return topic

        return None

    def pick_n_topics(self, archetype: str, n: int) -> list[TopicEntry]:
        """Pick up to N distinct unused topics and mark them all used atomically.

        Calling this once from the main thread before spawning parallel workers
        avoids the race condition where two threads both read the same "unused"
        topic and mark it used independently.

        Returns a list of up to min(n, available) topics.
        """
        topics = self._load_bank(archetype)
        if not topics:
            return []

        unused = [t for t in topics if not self.db.is_topic_used(archetype, t.slug)]
        if not unused:
            return []

        # Pick min(n, available) unique topics without replacement
        chosen = random.sample(unused, min(n, len(unused)))

        # Mark all chosen topics used before any thread starts generating
        for t in chosen:
            self.db.mark_topic_used(archetype, t.slug)

        return chosen

    def list_topics(self, archetype: str) -> list[TopicEntry]:
        """List all topics for an archetype."""
        return self._load_bank(archetype)

    def count_remaining(self, archetype: str) -> int:
        """Count unused topics for an archetype."""
        topics = self._load_bank(archetype)
        return sum(1 for t in topics if not self.db.is_topic_used(archetype, t.slug))

    def _load_bank(self, archetype: str) -> list[TopicEntry]:
        """Load topics from the YAML file for this archetype."""
        bank_file = self.banks_dir / f"{archetype}.yaml"
        if not bank_file.exists():
            return []

        with open(bank_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw_topics = data.get("topics", [])
        return [TopicEntry(**t) for t in raw_topics]
