"""Content generator — loads archetype prompts, calls LLM, validates output."""

from __future__ import annotations

import json
from typing import Any

from jinja2 import Template

from ..config import Config
from ..models import PostDraft, TopicEntry
from .llm import LLMClient


class ContentGenerator:
    """Generate XHS post content for a given archetype and topic."""

    def __init__(self, config: Config, llm: LLMClient | None = None):
        self.config = config
        self.llm = llm or LLMClient.from_config(config.llm)
        self._prompts_dir = config.base_dir / "config" / "prompts"

    def generate(self, archetype: str, topic: TopicEntry) -> tuple[PostDraft, str]:
        """Generate a post draft for the given archetype and topic.

        Returns (PostDraft, payload_json).
        """
        prompt = self._render_prompt(archetype, topic)
        raw = self.llm.generate_json(prompt)

        # Post-process: safety disclaimer
        if raw.get("safety_disclaimer_needed"):
            disclaimer = self.config.content.get("safety_disclaimer", "")
            if disclaimer and disclaimer not in raw.get("body", ""):
                raw["body"] = raw["body"].rstrip() + f"\n\n⚠️ {disclaimer}"

        # Post-process: ensure default tags
        default_tags = self.config.content.get("default_tags", [])
        existing_tags = raw.get("tags", [])
        for tag in default_tags:
            if tag not in existing_tags:
                existing_tags.append(tag)
        raw["tags"] = existing_tags

        # Post-process: AI label
        ai_label = self.config.content.get("ai_label", "")
        if ai_label and ai_label not in raw.get("body", ""):
            raw["body"] = raw["body"].rstrip() + f"\n\n{ai_label}"

        # Post-process: safety filter
        from ..safety import check_and_fix

        safety_result, fixed_body = check_and_fix(
            title=raw.get("title", ""),
            body=raw.get("body", ""),
            tags=raw.get("tags", []),
            safety_disclaimer_needed=raw.get("safety_disclaimer_needed", False),
            safety_disclaimer=self.config.content.get("safety_disclaimer", ""),
        )
        raw["body"] = fixed_body

        if not safety_result.passed:
            raise ContentBlockedError(
                f"Content blocked by safety filter: {safety_result.blocks}"
            )

        if safety_result.warnings:
            import logging

            logger = logging.getLogger("zcyber.safety")
            for warning in safety_result.warnings:
                logger.warning(f"Safety warning: {warning}")

        draft = PostDraft(**raw)
        payload = json.dumps(raw, ensure_ascii=False, indent=2)
        return draft, payload


class ContentBlockedError(Exception):
    """Raised when generated content fails safety checks."""

    def _render_prompt(self, archetype: str, topic: TopicEntry) -> str:
        """Load and render the Jinja2 prompt template for the archetype."""
        template_path = self._prompts_dir / f"{archetype}.j2"
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        template_text = template_path.read_text(encoding="utf-8")
        template = Template(template_text)

        # Build template variables from topic — pass all fields
        variables = self._build_template_vars(topic)
        return template.render(**variables)

    def _build_template_vars(self, topic: TopicEntry) -> dict[str, Any]:
        """Build the full set of Jinja2 template variables from a topic."""
        # Start with all TopicEntry fields
        variables = topic.model_dump()

        # Add config-level content settings
        variables["cta"] = self.config.content.get("cta", "")
        variables["safety_disclaimer"] = self.config.content.get("safety_disclaimer", "")
        variables["default_tags"] = self.config.content.get("default_tags", [])

        # news_hook specific aliases
        variables["news_source"] = topic.news_url.split("/")[2] if topic.news_url else ""

        return variables
