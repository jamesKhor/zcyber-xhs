"""Topic discovery from YAML topic banks, with dedup against history."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import yaml

from ..db import Database
from ..models import TopicEntry


class TopicBank:
    """Load topics from YAML banks and pick unused ones."""

    def __init__(self, config_dir: Path, db: Database):
        self.banks_dir = config_dir / "topic_banks"
        self.db = db

    def pick_topic(self, archetype: str) -> Optional[TopicEntry]:
        """Pick a random unused topic for the given archetype.

        Returns None if all topics have been used.
        """
        results = self.pick_n_topics(archetype, 1)
        return results[0] if results else None

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
