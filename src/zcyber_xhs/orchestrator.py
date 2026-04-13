"""Orchestrator — the main pipeline: discover -> generate -> render -> queue."""

from __future__ import annotations

import json
from typing import Optional

import click

from .config import Config
from .db import Database
from .discover.rss import RSSDiscovery
from .discover.topic_bank import TopicBank
from .generate.generator import ContentGenerator
from .generate.llm import LLMClient
from .images.renderer import ImageRenderer
from .models import PostDraft, TopicEntry
from .queue import DraftQueue

# Archetypes that use YAML topic banks
BANK_ARCHETYPES = {
    "problem_command", "tool_spotlight", "everyday_panic",
    "before_after", "mythbust",
}


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
        """Run the full pipeline for one post. Returns post ID or None."""
        # 1. Discover topic
        topic = self._pick_topic(archetype, topic_override)
        if not topic:
            click.echo(f"No unused topics for archetype '{archetype}'")
            return None

        click.echo(f"Topic: {topic.slug} -- {topic.problem}")

        # 2. Generate content (with safety retry)
        click.echo("Generating content via LLM...")
        draft, payload_json = self._generate_with_retry(archetype, topic)
        click.echo(f"Title: {draft.title}")

        # 3. Render image(s)
        image_path = self._render_images(draft, archetype, topic.slug)

        # 4. Enqueue
        post_id = self.queue.enqueue(draft, topic.slug, image_path, payload_json)
        click.echo(
            f"Draft queued (id={post_id}). "
            f"Use 'zcyber queue approve {post_id}' to publish."
        )

        # 5. If CTF, also queue the solution post
        if archetype == "ctf" and draft.solution_body:
            self._queue_ctf_solution(draft, topic.slug, payload_json)

        return post_id

    def _generate_with_retry(
        self, archetype: str, topic: TopicEntry, max_retries: int = 2
    ) -> tuple[PostDraft, str]:
        """Generate content with auto-retry on safety filter blocks."""
        from .generate.generator import ContentBlockedError

        for attempt in range(1, max_retries + 2):
            try:
                return self.generator.generate(archetype, topic)
            except ContentBlockedError as e:
                if attempt <= max_retries:
                    click.echo(f"Safety filter blocked (attempt {attempt}), retrying...")
                else:
                    raise RuntimeError(
                        f"Content blocked after {max_retries + 1} attempts: {e}"
                    ) from e

    def _pick_topic(
        self, archetype: str, topic_override: Optional[str]
    ) -> Optional[TopicEntry]:
        """Pick a topic based on archetype type."""
        if topic_override:
            return self._pick_override(archetype, topic_override)

        if archetype == "news_hook":
            return self._pick_news_topic()

        if archetype == "ctf":
            # CTF generates its own puzzle — use a placeholder topic
            return TopicEntry(slug="ctf-weekly", problem="weekly CTF challenge")

        if archetype in BANK_ARCHETYPES:
            return self.topic_bank.pick_topic(archetype)

        return None

    def _pick_override(
        self, archetype: str, topic_override: str
    ) -> Optional[TopicEntry]:
        """Use a specific topic slug from the bank."""
        topics = self.topic_bank.list_topics(archetype)
        match = [t for t in topics if t.slug == topic_override]
        if match:
            self.db.mark_topic_used(archetype, match[0].slug)
            return match[0]
        return TopicEntry(
            slug=topic_override,
            problem=topic_override.replace("-", " "),
        )

    def _pick_news_topic(self) -> Optional[TopicEntry]:
        """Pick a topic from the zcybernews RSS feed."""
        rss = RSSDiscovery(self.db)
        return rss.pick_topic()

    def _render_images(
        self, draft: PostDraft, archetype: str, topic_slug: str
    ) -> Optional[str]:
        """Render image(s) and return the path(s) as a string."""
        if draft.image_mode == "carousel" and draft.carousel_slides:
            return self._render_carousel(draft, archetype, topic_slug)

        if draft.image_mode == "text_card":
            return self._render_single(draft, archetype, topic_slug)

        return None

    def _render_single(
        self, draft: PostDraft, archetype: str, topic_slug: str
    ) -> str:
        """Render a single text card image."""
        click.echo(f"Rendering image ({draft.image_template})...")
        output = self.renderer.render_sync(draft, f"{archetype}_{topic_slug}")
        click.echo(f"Image saved: {output}")
        return str(output)

    def _render_carousel(
        self, draft: PostDraft, archetype: str, topic_slug: str
    ) -> str:
        """Render carousel slides and return paths as JSON list."""
        click.echo(f"Rendering {len(draft.carousel_slides)} carousel slides...")

        # Create a PostDraft per slide for the renderer
        slide_drafts = []
        for slide_data in draft.carousel_slides:
            slide_draft = PostDraft(
                archetype=draft.archetype,
                title=draft.title,
                body=draft.body,
                image_mode="text_card",
                image_template=draft.image_template,
                image_text=slide_data,
                safety_disclaimer_needed=draft.safety_disclaimer_needed,
            )
            slide_drafts.append(slide_draft)

        paths = self.renderer.render_carousel_sync(
            slide_drafts, f"{archetype}_{topic_slug}"
        )
        path_strs = [str(p) for p in paths]
        click.echo(f"Carousel saved: {len(path_strs)} slides")

        # Return as JSON array of paths
        return json.dumps(path_strs, ensure_ascii=False)

    def _queue_ctf_solution(
        self, draft: PostDraft, topic_slug: str, payload_json: str
    ) -> None:
        """Queue the CTF solution as a separate draft post."""
        if not draft.solution_image_text:
            return

        solution_draft = PostDraft(
            archetype=draft.archetype,
            title=f"[答案揭晓] {draft.title}",
            body=draft.solution_body,
            tags=draft.tags,
            image_mode="text_card",
            image_template="terminal_dark",
            image_text=draft.solution_image_text,
            cta=draft.cta,
        )

        # Render solution image
        image_path = self._render_single(
            solution_draft, "ctf_solution", topic_slug
        )

        solution_id = self.queue.enqueue(
            solution_draft, f"{topic_slug}_solution", image_path, payload_json
        )
        click.echo(
            f"CTF solution queued (id={solution_id}). "
            "Approve after the challenge post is published."
        )
