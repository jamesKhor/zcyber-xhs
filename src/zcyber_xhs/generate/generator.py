"""Content generator — loads archetype prompts, calls LLM, validates output."""

from __future__ import annotations

import json
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..config import Config
from ..models import PostDraft, TopicEntry
from .llm import LLMClient


class ContentGenerator:
    """Generate XHS post content for a given archetype and topic."""

    def __init__(self, config: Config, llm: LLMClient | None = None):
        self.config = config
        self.llm = llm or LLMClient.from_config(config.llm)
        self._prompts_dir = config.base_dir / "config" / "prompts"

    def generate(
        self, archetype: str, topic: TopicEntry, language: str = "zh"
    ) -> tuple[PostDraft, str]:
        """Generate a post draft for the given archetype and topic.

        Returns (PostDraft, payload_json).
        """
        prompt = self._render_prompt(archetype, topic, language=language)
        raw = self.llm.generate_json(prompt)

        # Post-process: enforce XHS 20-char title limit
        # XHS platform rejects titles > 20 chars (Chinese + English + digits each = 1 char).
        # The prompt already instructs ≤20 chars; this is the safety net.
        title = raw.get("title", "")
        if len(title) > 20:
            import logging
            logger = logging.getLogger("zcyber.generator")
            logger.warning(f"Title over limit ({len(title)} chars): {title!r}")
            # Smart truncation: prefer cutting at the last natural break ≤20 chars
            # so the title stays grammatically clean rather than mid-word.
            # Priority: Chinese punctuation > space (word boundary) > hard cut at 20.
            _PUNCT_CHARS = set("，。！？：；、…「」『』【】")
            cut = 20
            space_cut = None
            for i in range(19, 9, -1):   # scan back from pos 19 to pos 10
                if title[i] in _PUNCT_CHARS:
                    cut = i          # cut before the trailing punctuation
                    space_cut = None  # punct wins, clear space fallback
                    break
                if title[i] == " " and space_cut is None:
                    space_cut = i    # remember last space as fallback
            if cut == 20 and space_cut is not None:
                cut = space_cut      # fall back to last word boundary
            raw["title"] = title[:cut]
            logger.warning(f"Title smart-truncated to {cut} chars: {raw['title']!r}")

        # Post-process: safety disclaimer
        if raw.get("safety_disclaimer_needed"):
            disclaimer = self.config.content.get("safety_disclaimer", "")
            if disclaimer and disclaimer not in raw.get("body", ""):
                raw["body"] = raw["body"].rstrip() + f"\n\n⚠️ {disclaimer}"

        # Post-process: ensure default tags (cap total at 7 to avoid XHS shadowban)
        if language == "en":
            default_tags = self.config.content.get(
                "en_default_tags", self.config.content.get("default_tags", [])
            )
        else:
            default_tags = self.config.content.get("default_tags", [])
        existing_tags = raw.get("tags", [])
        # Trim LLM tags to 4 max, then append defaults (keeps total ≤ 7)
        trimmed_llm_tags = existing_tags[:4]
        for tag in default_tags:
            if tag not in trimmed_llm_tags:
                trimmed_llm_tags.append(tag)
        raw["tags"] = trimmed_llm_tags[:7]  # hard cap at 7

        # Post-process: append the configured CTA to body (career_cta for career archetypes).
        # The LLM outputs a `cta` field in JSON but the body only gets the LLM's own
        # engagement question — the config CTA would be silently lost without this step.
        cta_text = raw.get("cta", "")
        if cta_text and cta_text not in raw.get("body", ""):
            raw["body"] = raw["body"].rstrip() + f"\n\n{cta_text}"

        # Post-process: education disclaimer (always appended for cyber content)
        edu_disclaimer = self.config.content.get("education_disclaimer", "")
        if edu_disclaimer and edu_disclaimer not in raw.get("body", ""):
            raw["body"] = raw["body"].rstrip() + f"\n\n📚 {edu_disclaimer}"

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
        draft.language = language
        payload = json.dumps(raw, ensure_ascii=False, indent=2)
        return draft, payload

    def _render_prompt(self, archetype: str, topic: TopicEntry, language: str = "zh") -> str:
        """Load and render the Jinja2 prompt template for the archetype."""
        # English: look in prompts/en/{archetype}_en.j2, fall back to zh if not found
        if language == "en":
            en_path = self._prompts_dir / "en" / f"{archetype}_en.j2"
            template_name = f"en/{archetype}_en.j2" if en_path.exists() else f"{archetype}.j2"
        else:
            template_name = f"{archetype}.j2"

        full_path = self._prompts_dir / template_name
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {full_path}")

        env = Environment(
            loader=FileSystemLoader(str(self._prompts_dir), encoding="utf-8")
        )
        template = env.get_template(template_name)
        variables = self._build_template_vars(topic, archetype=archetype, language=language)
        return template.render(**variables)

    _CAREER_ARCHETYPES = frozenset({
        "cert_war", "salary_map", "career_entry",
        "day_in_life", "interview_intel", "exam_reality", "career_myth",
    })

    def _build_template_vars(
        self, topic: TopicEntry, archetype: str = "", language: str = "zh"
    ) -> dict[str, Any]:
        """Build the full set of Jinja2 template variables from a topic."""
        variables = topic.model_dump()

        if language == "en":
            variables["cta"] = self.config.content.get("en_cta", self.config.content.get("cta", ""))
            variables["safety_disclaimer"] = self.config.content.get(
                "en_safety_disclaimer", self.config.content.get("safety_disclaimer", "")
            )
            variables["default_tags"] = self.config.content.get(
                "en_default_tags", self.config.content.get("default_tags", [])
            )
        else:
            # Career archetypes use a different CTA tone (aspirational vs threat intel)
            if archetype in self._CAREER_ARCHETYPES:
                variables["cta"] = self.config.content.get(
                    "career_cta", self.config.content.get("cta", "")
                )
            else:
                variables["cta"] = self.config.content.get("cta", "")
            variables["safety_disclaimer"] = self.config.content.get("safety_disclaimer", "")
            variables["default_tags"] = self.config.content.get("default_tags", [])

        # news_hook specific aliases
        variables["news_source"] = topic.news_url.split("/")[2] if topic.news_url else ""

        return variables


class ContentBlockedError(Exception):
    """Raised when generated content fails safety checks."""
