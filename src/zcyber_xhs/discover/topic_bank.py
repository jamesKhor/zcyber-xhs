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
        topics = self._load_bank(archetype)
        if not topics:
            return None

        # Filter out already-used topics
        unused = [t for t in topics if not self.db.is_topic_used(archetype, t.slug)]

        if not unused:
            # All used — could reset or return None
            return None

        topic = random.choice(unused)
        self.db.mark_topic_used(archetype, topic.slug)
        return topic

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
