"""Pydantic models for the content pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Archetype(str, Enum):
    # ── Threat / awareness rotation ──────────────────────────────────────
    PROBLEM_COMMAND = "problem_command"
    TOOL_SPOTLIGHT = "tool_spotlight"   # kept for DB backwards-compat
    EVERYDAY_PANIC = "everyday_panic"
    BEFORE_AFTER = "before_after"       # kept for DB backwards-compat
    NEWS_HOOK = "news_hook"
    MYTHBUST = "mythbust"
    CTF = "ctf"
    REAL_STORY = "real_story"           # Tue: humanised breach narrative
    RANK_WAR = "rank_war"               # Thu: opinion poll / debate
    HACKER_POV = "hacker_pov"          # Sun: immersive 2nd-person scenario
    # ── Career / education rotation (XHS pivot) ──────────────────────────
    CERT_WAR = "cert_war"               # Mon/Thu/Sun: head-to-head cert comparison
    SALARY_MAP = "salary_map"           # Tue/Sat: real salary bands by market/role
    CAREER_ENTRY = "career_entry"       # Wed/Fri: break-in roadmap for non-security people
    DAY_IN_LIFE = "day_in_life"         # Fri: hour-by-hour real career day POV
    INTERVIEW_INTEL = "interview_intel" # Thu: real interview questions + insider intel
    EXAM_REALITY = "exam_reality"       # Sun: raw cert exam experience (pass/fail)
    CAREER_MYTH = "career_myth"         # Monthly: debunking career myths with data


class PostStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"


class ImageText(BaseModel):
    """Flexible image text data — fields used vary by archetype template."""

    model_config = {"extra": "allow"}

    # Common
    headline: str = ""
    command: str = ""
    output_preview: str = ""
    caption: str = ""

    # ── carousel_slide fields ──────────────────────────────────────────────
    # slide_type: "hook" | "point" | "cta"
    slide_type: str = "point"
    # body_text: main paragraph text on point/cta slides
    body_text: str = ""
    # point_number: displayed badge e.g. "01", "02"
    point_number: str = ""
    # emoji: large emoji on the hook slide
    emoji: str = ""
    # chip_label: small category chip e.g. "钓鱼攻击", "密码安全"
    chip_label: str = ""
    # steps: list of action-item strings for the CTA slide
    steps: list[str] = Field(default_factory=list)

    # tool_spotlight carousel
    tool_name: str = ""
    use_number: str = ""
    use_title: str = ""
    items: list[dict[str, str]] = Field(default_factory=list)

    # everyday_panic
    scenario_emoji: str = ""

    # before_after / split_compare
    before_label: str = ""
    after_label: str = ""
    before_text: str = ""
    after_text: str = ""

    # news_hook / alert_red
    severity: str = ""
    source: str = ""
    date: str = ""

    # mythbust
    myth: str = ""
    truth: str = ""

    # ctf / puzzle_frame
    puzzle_string: str = ""
    hint: str = ""
    difficulty: str = ""
    engagement_cta: str = ""

    # hacker_pov
    pov_label: str = ""


class PostDraft(BaseModel):
    """Structured output from the LLM content generator."""

    archetype: Archetype
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    language: str = "zh"    # "zh" = Chinese/XHS, "en" = English/Instagram
    image_mode: str = "text_card"
    image_template: str = "terminal_dark"
    image_text: ImageText = Field(default_factory=ImageText)
    cta: str = ""
    safety_disclaimer_needed: bool = False

    # carousel: list of per-slide image_text for multi-image posts
    carousel_slides: list[ImageText] = Field(default_factory=list)

    # ctf: solution post data
    solution_body: str = ""
    solution_image_text: Optional[ImageText] = None


class PostRecord(BaseModel):
    """A post as stored in the database."""

    id: Optional[int] = None
    archetype: str
    topic_slug: str
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    image_path: Optional[str] = None
    payload_json: Optional[str] = None
    status: PostStatus = PostStatus.DRAFT
    scheduled_for: Optional[datetime] = None
    published_url: Optional[str] = None
    published_at: Optional[datetime] = None
    metrics_json: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TopicEntry(BaseModel):
    """A topic from the topic bank — flexible fields per archetype."""

    model_config = {"extra": "allow"}

    slug: str
    problem: str = ""
    tool: str = ""
    command: str = ""
    category: str = ""

    # everyday_panic
    scenario: str = ""
    solution: str = ""

    # before_after
    bad_practice: str = ""
    good_practice: str = ""

    # mythbust
    myth: str = ""
    truth: str = ""

    # tool_spotlight
    uses: list[dict[str, str]] = Field(default_factory=list)

    # news_hook (from RSS)
    news_title: str = ""
    news_url: str = ""
    news_excerpt: str = ""
    news_date: str = ""
    news_category: str = ""

    # hacker_pov
    pov_type: str = ""
    attack_type: str = ""
    technical_detail: str = ""
    defense_action: str = ""
