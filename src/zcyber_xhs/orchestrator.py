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

# Archetypes that use YAML topic banks (threat rotation)
_THREAT_ARCHETYPES = {
    "problem_command", "tool_spotlight", "everyday_panic",
    "before_after", "mythbust",
    "real_story", "rank_war", "hacker_pov",
}

# Career/education archetypes (XHS pivot — aspirational, not scary)
_CAREER_ARCHETYPES = {
    "cert_war", "salary_map", "career_entry",
}

BANK_ARCHETYPES = _THREAT_ARCHETYPES | _CAREER_ARCHETYPES


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
        text_only: bool = False,
        language: str = "zh",
    ) -> Optional[int]:
        """Run the full pipeline for one post. Returns post ID or None.

        Args:
            text_only: If True, skip image rendering (fast mode).
                       Call render_image_for_post(post_id) later to render.
            language: Content language — "zh" (default) or "en".
        """
        # 1. Discover topic
        topic = self._pick_topic(archetype, topic_override)
        if not topic:
            click.echo(
                f"No topic available for archetype '{archetype}'. "
                "YAML bank exhausted and LLM dynamic generation also failed. "
                "Check your DEEPSEEK_API_KEY or add topics to the YAML bank."
            )
            return None

        click.echo(f"Topic: {topic.slug} -- {topic.problem}")

        # 2. Generate content (with safety retry)
        click.echo("Generating content via LLM...")
        draft, payload_json = self._generate_with_retry(archetype, topic, language=language)
        click.echo(f"Title: {draft.title}")

        # 3. Render image(s) — skipped in text_only mode
        if text_only:
            image_path = None
            click.echo("Text-only mode — image rendering skipped.")
        else:
            image_path = self._render_images(draft, archetype, topic.slug)

        # 4. Enqueue
        post_id = self.queue.enqueue(draft, topic.slug, image_path, payload_json)
        click.echo(
            f"Draft queued (id={post_id}). "
            f"Use 'zcyber queue approve {post_id}' to publish."
        )

        # 5. If CTF, also queue the solution post
        if archetype == "ctf" and draft.solution_body:
            self._queue_ctf_solution(draft, topic.slug, payload_json, text_only=text_only)

        return post_id

    def render_image_for_post(self, post_id: int, force: bool = False) -> Optional[str]:
        """Render image(s) for a draft and save to DB.

        Reconstructs the PostDraft from the stored payload_json so the LLM
        does not need to be called again.  Returns the saved image path.

        Args:
            force: If True, re-render even if an image already exists
                   (useful after template updates).
        """
        from .models import Archetype, PostDraft  # local import avoids circularity

        post = self.db.get_post(post_id)
        if not post:
            click.echo(f"Post #{post_id} not found.")
            return None

        if post.image_path and not force:
            click.echo(f"Post #{post_id} already has an image — skipping render.")
            return post.image_path

        if not post.payload_json:
            click.echo(f"Post #{post_id} has no payload_json — cannot reconstruct draft.")
            return None

        payload = json.loads(post.payload_json)

        # Reconstruct a PostDraft from stored payload — only image fields matter
        # image_text must be an ImageText object — deserialise from dict or use empty
        from .models import ImageText  # local import avoids circularity
        raw_image_text = payload.get("image_text") or {}
        if isinstance(raw_image_text, dict):
            image_text_obj = ImageText(**raw_image_text)
        elif isinstance(raw_image_text, ImageText):
            image_text_obj = raw_image_text
        else:
            image_text_obj = ImageText(headline=post.title or "")

        draft = PostDraft(
            archetype=Archetype(post.archetype),
            title=post.title or "",
            body=post.body or "",
            tags=post.tags or [],
            image_mode=payload.get("image_mode", "text_card"),
            image_template=payload.get("image_template", "terminal_dark"),
            image_text=image_text_obj,
            carousel_slides=payload.get("carousel_slides") or [],
            safety_disclaimer_needed=payload.get("safety_disclaimer_needed", False),
            cta=payload.get("cta", ""),
        )

        image_path = self._render_images(draft, post.archetype, post.topic_slug)
        if image_path:
            self.db.update_post_image(post_id, image_path)
            click.echo(f"Image rendered and saved for post #{post_id}: {image_path}")
        return image_path

    def _generate_with_retry(
        self, archetype: str, topic: TopicEntry, max_retries: int = 2, language: str = "zh"
    ) -> tuple[PostDraft, str]:
        """Generate content with auto-retry on safety filter blocks."""
        from .generate.generator import ContentBlockedError

        for attempt in range(1, max_retries + 2):
            try:
                return self.generator.generate(archetype, topic, language=language)
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
            return self.topic_bank.pick_topic(archetype, llm=self.llm)

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

    def render_images_for_posts(self, post_ids: list[int]) -> dict[int, str]:
        """Render images for multiple text-only drafts. Returns {post_id: image_path}.

        Text-card posts are batched into ONE browser session (fast).
        Carousel posts are rendered individually (each needs its own slide set).
        """
        from .models import Archetype, ImageText  # local import

        def _build_draft(post, payload):
            raw_it = payload.get("image_text") or {}
            image_text_obj = (
                ImageText(**raw_it) if isinstance(raw_it, dict) else ImageText()
            )
            return PostDraft(
                archetype=Archetype(post.archetype),
                title=post.title or "",
                body=post.body or "",
                tags=post.tags or [],
                image_mode=payload.get("image_mode", "text_card"),
                image_template=payload.get("image_template", "terminal_dark"),
                image_text=image_text_obj,
                carousel_slides=payload.get("carousel_slides") or [],
                safety_disclaimer_needed=payload.get("safety_disclaimer_needed", False),
                cta=payload.get("cta", ""),
            )

        # Split into text_card (batchable) vs carousel (must render individually)
        text_card_items: list[tuple[int, object, PostDraft, str]] = []
        carousel_items: list[tuple[int, object, PostDraft]] = []

        for post_id in post_ids:
            post = self.db.get_post(post_id)
            if not post or post.image_path or not post.payload_json:
                continue
            payload = json.loads(post.payload_json)
            draft = _build_draft(post, payload)
            filename = f"{post.archetype}_{post.topic_slug}"
            if draft.image_mode == "carousel":
                carousel_items.append((post_id, post, draft))
            else:
                text_card_items.append((post_id, post, draft, filename))

        results: dict[int, str] = {}

        # Batch render all text cards in one browser session
        if text_card_items:
            click.echo(f"Batch rendering {len(text_card_items)} text-card image(s)...")
            batch_input = [(draft, fname) for _, _, draft, fname in text_card_items]
            paths = self.renderer.render_batch_sync(batch_input)
            for (post_id, _, _, _), path in zip(text_card_items, paths):
                path_str = str(path)
                self.db.update_post_image(post_id, path_str)
                results[post_id] = path_str
                click.echo(f"  ✓ Post #{post_id}: {path_str}")

        # Render carousel posts individually
        for post_id, post, draft in carousel_items:
            click.echo(f"Rendering carousel for post #{post_id}...")
            path = self._render_carousel(draft, post.archetype, post.topic_slug)
            if path:
                self.db.update_post_image(post_id, path)
                results[post_id] = path
                click.echo(f"  ✓ Post #{post_id}: {path}")

        return results

    def _queue_ctf_solution(
        self, draft: PostDraft, topic_slug: str, payload_json: str,
        text_only: bool = False,
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

        # Render solution image (skip in text_only mode)
        if text_only:
            image_path = None
            click.echo("Text-only mode — CTF solution image rendering skipped.")
        else:
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
