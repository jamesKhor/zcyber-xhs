"""Pydantic models for the content pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Archetype(str, Enum):
    PROBLEM_COMMAND = "problem_command"
    TOOL_SPOTLIGHT = "tool_spotlight"
    EVERYDAY_PANIC = "everyday_panic"
    BEFORE_AFTER = "before_after"
    NEWS_HOOK = "news_hook"
    MYTHBUST = "mythbust"
    CTF = "ctf"


class PostStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"


class ImageText(BaseModel):
    headline: str
    command: str = ""
    output_preview: str = ""
    caption: str = ""


class PostDraft(BaseModel):
    """Structured output from the LLM content generator."""

    archetype: Archetype
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    image_mode: str = "text_card"
    image_template: str = "terminal_dark"
    image_text: ImageText = Field(default_factory=ImageText)
    cta: str = ""
    safety_disclaimer_needed: bool = False


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
    """A topic from the topic bank."""

    slug: str
    problem: str
    tool: str
    command: str
    category: str = ""
