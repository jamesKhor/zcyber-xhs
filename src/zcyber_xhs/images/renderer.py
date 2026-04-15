"""Image renderer — Playwright HTML→PNG for XHS text cards."""

from __future__ import annotations

import asyncio
import base64
import random
import sys
from pathlib import Path
from typing import Any, Coroutine, TypeVar

from jinja2 import Template

from ..config import Config
from ..models import PostDraft

T = TypeVar("T")


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine safely on any platform/thread.

    On Windows, SelectorEventLoop does not support subprocess (needed by
    Playwright to launch Chromium).  We always use ProactorEventLoop on
    Windows so Playwright can start its browser process regardless of what
    the calling thread's current event loop policy is.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    else:
        return asyncio.run(coro)


class ImageRenderer:
    """Render post drafts into 1080x1440 PNG text cards."""

    def __init__(self, config: Config):
        self.config = config
        self.templates_dir = Path(__file__).parent / "templates"
        self.backgrounds_dir = config.base_dir / "config" / "backgrounds"
        self.output_dir = config.base_dir / config.images.get("output_dir", "output/images")
        self.width = config.images.get("width", 1080)
        self.height = config.images.get("height", 1440)

    def _pick_background(self, template_name: str) -> str | None:
        """Pick a random background image and return as base64 data URI."""
        bg_dir = self.backgrounds_dir / template_name
        if not bg_dir.exists():
            return None

        images = list(bg_dir.glob("*.png")) + list(bg_dir.glob("*.jpg"))
        if not images:
            return None

        chosen = random.choice(images)
        data = chosen.read_bytes()
        suffix = chosen.suffix.lstrip(".")
        mime = "image/jpeg" if suffix in ("jpg", "jpeg") else "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def _build_template_vars(self, draft: PostDraft) -> dict:
        """Build the full set of template variables from a draft."""
        bg_uri = self._pick_background(draft.image_template)

        return {
            # Common vars
            "headline": draft.image_text.headline,
            "command": draft.image_text.command,
            "output_preview": draft.image_text.output_preview,
            "caption": draft.image_text.caption,
            "cta": self.config.content.get("cta", ""),
            "safety_disclaimer": (
                self.config.content.get("safety_disclaimer", "")
                if draft.safety_disclaimer_needed
                else ""
            ),
            "background_image": bg_uri,
            # Extended vars for specialized templates
            "items": getattr(draft.image_text, "items", []),
            "myth": getattr(draft.image_text, "myth", ""),
            "truth": getattr(draft.image_text, "truth", ""),
            "before_label": getattr(draft.image_text, "before_label", ""),
            "after_label": getattr(draft.image_text, "after_label", ""),
            "before_text": getattr(draft.image_text, "before_text", ""),
            "after_text": getattr(draft.image_text, "after_text", ""),
            "puzzle_string": getattr(draft.image_text, "puzzle_string", ""),
            "hint": getattr(draft.image_text, "hint", ""),
            "difficulty": getattr(draft.image_text, "difficulty", ""),
            "severity": getattr(draft.image_text, "severity", ""),
            "source": getattr(draft.image_text, "source", ""),
            "date": getattr(draft.image_text, "date", ""),
            "tool_name": getattr(draft.image_text, "tool_name", ""),
            "use_number": getattr(draft.image_text, "use_number", ""),
            "use_title": getattr(draft.image_text, "use_title", ""),
            "engagement_cta": getattr(draft.image_text, "engagement_cta", ""),
        }

    async def render(self, draft: PostDraft, filename: str) -> Path:
        """Render a single post draft to a PNG image."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{filename}.png"

        template_file = self.templates_dir / f"{draft.image_template}.html"
        if not template_file.exists():
            raise FileNotFoundError(f"Image template not found: {template_file}")

        html_template = template_file.read_text(encoding="utf-8")
        template = Template(html_template)
        variables = self._build_template_vars(draft)
        html_content = template.render(**variables)

        await self._screenshot(html_content, output_path)
        return output_path

    async def render_carousel(
        self, drafts: list[PostDraft], filename_prefix: str
    ) -> list[Path]:
        """Render multiple slides for a carousel post (e.g. tool_spotlight)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        for i, draft in enumerate(drafts):
            output_path = self.output_dir / f"{filename_prefix}_{i + 1}.png"

            template_file = self.templates_dir / f"{draft.image_template}.html"
            if not template_file.exists():
                raise FileNotFoundError(f"Image template not found: {template_file}")

            html_template = template_file.read_text(encoding="utf-8")
            template = Template(html_template)
            variables = self._build_template_vars(draft)
            variables["slide_number"] = i + 1
            variables["total_slides"] = len(drafts)
            html_content = template.render(**variables)

            await self._screenshot(html_content, output_path)
            paths.append(output_path)

        return paths

    async def _screenshot(
        self, html_content: str, output_path: Path, browser=None
    ) -> None:
        """Take a screenshot of rendered HTML.

        If a browser instance is provided it is reused (no launch overhead).
        Otherwise a short-lived browser is created just for this call.
        """
        from playwright.async_api import async_playwright

        async def _do_screenshot(b) -> None:
            page = await b.new_page(
                viewport={"width": self.width, "height": self.height},
                device_scale_factor=2,
            )
            await page.set_content(html_content, wait_until="networkidle")
            # Extra safety margin for Google Fonts to finish rendering
            # (networkidle fires when requests complete but paint may lag)
            await page.wait_for_timeout(800)
            await page.screenshot(path=str(output_path), type="png")
            await page.close()

        if browser is not None:
            await _do_screenshot(browser)
        else:
            async with async_playwright() as p:
                b = await p.chromium.launch()
                await _do_screenshot(b)
                await b.close()

    async def render_batch(
        self, items: list[tuple[PostDraft, str]]
    ) -> list[Path]:
        """Render N images in a SINGLE browser session — much faster for batches.

        Args:
            items: list of (draft, filename) pairs.
        Returns:
            list of output Paths in the same order.
        """
        from playwright.async_api import async_playwright

        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                for draft, filename in items:
                    output_path = self.output_dir / f"{filename}.png"
                    template_file = self.templates_dir / f"{draft.image_template}.html"
                    if not template_file.exists():
                        raise FileNotFoundError(
                            f"Image template not found: {template_file}"
                        )
                    html_content = Template(
                        template_file.read_text(encoding="utf-8")
                    ).render(**self._build_template_vars(draft))
                    await self._screenshot(html_content, output_path, browser=browser)
                    paths.append(output_path)
            finally:
                await browser.close()

        return paths

    def render_sync(self, draft: PostDraft, filename: str) -> Path:
        """Synchronous wrapper for render()."""
        return _run_async(self.render(draft, filename))

    def render_carousel_sync(
        self, drafts: list[PostDraft], filename_prefix: str
    ) -> list[Path]:
        """Synchronous wrapper for render_carousel()."""
        return _run_async(self.render_carousel(drafts, filename_prefix))

    def render_batch_sync(
        self, items: list[tuple[PostDraft, str]]
    ) -> list[Path]:
        """Synchronous wrapper for render_batch() — single browser session."""
        return _run_async(self.render_batch(items))
