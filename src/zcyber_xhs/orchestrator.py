"""Orchestrator — the main pipeline: discover → generate → render → queue."""

from __future__ import annotations

from typing import Optional

import click

from .config import Config
from .db import Database
from .discover.topic_bank import TopicBank
from .generate.generator import ContentGenerator
from .generate.llm import LLMClient
from .images.renderer import ImageRenderer
from .models import TopicEntry
from .queue import DraftQueue


class Orchestrator:
    """Runs the full content pipeline for a given archetype."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.topic_bank = TopicBank(config.base_dir / "config", db)
        self.llm = LLMClient.from_config(config.llm)
        self.generator = ContentGenerator(config, self.llm)
        self.renderer = ImageRenderer(config)
        self.queue = DraftQueue(config, db)

    def run(
        self,
        archetype: str,
        topic_override: Optional[str] = None,
    ) -> Optional[int]:
        """Run the full pipeline for one post.

        Args:
            archetype: The content archetype to generate.
            topic_override: Optional specific topic slug to use.

        Returns:
            The post ID if successful, None if no topic available.
        """
        # 1. Discover topic
        topic = self._pick_topic(archetype, topic_override)
        if not topic:
            click.echo(f"No unused topics for archetype '{archetype}'")
            return None

        click.echo(f"Topic: {topic.slug} — {topic.problem}")

        # 2. Generate content
        click.echo("Generating content via LLM...")
        draft, payload_json = self.generator.generate(archetype, topic)
        click.echo(f"Title: {draft.title}")

        # 3. Render image
        image_path: Optional[str] = None
        if draft.image_mode == "text_card":
            click.echo(f"Rendering image ({draft.image_template})...")
            output = self.renderer.render_sync(draft, f"{archetype}_{topic.slug}")
            image_path = str(output)
            click.echo(f"Image saved: {image_path}")

        # 4. Enqueue
        post_id = self.queue.enqueue(draft, topic.slug, image_path, payload_json)
        click.echo(f"Draft queued (id={post_id}). Use 'zcyber queue approve {post_id}' to publish.")

        return post_id

    def _pick_topic(
        self, archetype: str, topic_override: Optional[str]
    ) -> Optional[TopicEntry]:
        """Pick a topic from the bank, or use the override slug."""
        if topic_override:
            topics = self.topic_bank.list_topics(archetype)
            match = [t for t in topics if t.slug == topic_override]
            if match:
                self.db.mark_topic_used(archetype, match[0].slug)
                return match[0]
            # If not found in bank, create a minimal entry
            return TopicEntry(
                slug=topic_override,
                problem=topic_override.replace("-", " "),
                tool="",
                command="",
            )

        return self.topic_bank.pick_topic(archetype)
