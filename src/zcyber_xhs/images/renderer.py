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

    # Width / height for carousel slides (4:5 portrait — XHS/Instagram standard)
    CAROUSEL_WIDTH = 1080
    CAROUSEL_HEIGHT = 1350

    def _build_template_vars(self, draft: PostDraft) -> dict:
        """Build the full set of template variables from a draft."""
        bg_uri = self._pick_background(draft.image_template)
        it = draft.image_text

        return {
            # Common
            "headline": it.headline,
            "command": it.command,
            "output_preview": it.output_preview,
            "caption": it.caption,
            "cta": self.config.content.get("cta", ""),
            "safety_disclaimer": (
                self.config.content.get("safety_disclaimer", "")
                if draft.safety_disclaimer_needed
                else ""
            ),
            "background_image": bg_uri,
            # carousel_slide specific
            "slide_type": getattr(it, "slide_type", "point"),
            "body_text": getattr(it, "body_text", ""),
            "point_number": getattr(it, "point_number", ""),
            "emoji": getattr(it, "emoji", ""),
            "chip_label": getattr(it, "chip_label", ""),
            "steps": getattr(it, "steps", []),
            # Extended vars for legacy specialized templates
            "items": getattr(it, "items", []),
            "myth": getattr(it, "myth", ""),
            "truth": getattr(it, "truth", ""),
            "before_label": getattr(it, "before_label", ""),
            "after_label": getattr(it, "after_label", ""),
            "before_text": getattr(it, "before_text", ""),
            "after_text": getattr(it, "after_text", ""),
            "puzzle_string": getattr(it, "puzzle_string", ""),
            "hint": getattr(it, "hint", ""),
            "difficulty": getattr(it, "difficulty", ""),
            "severity": getattr(it, "severity", ""),
            "source": getattr(it, "source", ""),
            "date": getattr(it, "date", ""),
            "tool_name": getattr(it, "tool_name", ""),
            "use_number": getattr(it, "use_number", ""),
            "use_title": getattr(it, "use_title", ""),
            "engagement_cta": getattr(it, "engagement_cta", ""),
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
        """Render multiple slides for a carousel post.

        Carousel slides use CAROUSEL_WIDTH × CAROUSEL_HEIGHT (1080×1350)
        regardless of the global images config, since carousel tiles must
        fit the 4:5 portrait ratio expected by XHS and Instagram.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        total = len(drafts)

        for i, draft in enumerate(drafts):
            output_path = self.output_dir / f"{filename_prefix}_{i + 1}.png"

            template_file = self.templates_dir / f"{draft.image_template}.html"
            if not template_file.exists():
                raise FileNotFoundError(f"Image template not found: {template_file}")

            html_template = template_file.read_text(encoding="utf-8")
            template = Template(html_template)
            variables = self._build_template_vars(draft)
            variables["slide_number"] = i + 1
            variables["total_slides"] = total
            html_content = template.render(**variables)

            # Carousel slides get their own viewport dimensions
            await self._screenshot(
                html_content, output_path,
                width=self.CAROUSEL_WIDTH,
                height=self.CAROUSEL_HEIGHT,
            )
            paths.append(output_path)

        return paths

    async def _screenshot(
        self,
        html_content: str,
        output_path: Path,
        browser=None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Take a screenshot of rendered HTML.

        If a browser instance is provided it is reused (no launch overhead).
        Otherwise a short-lived browser is created just for this call.
        width/height override the global config dimensions (used for carousel).
        """
        from playwright.async_api import async_playwright

        vp_width = width if width is not None else self.width
        vp_height = height if height is not None else self.height

        async def _do_screenshot(b) -> None:
            page = await b.new_page(
                viewport={"width": vp_width, "height": vp_height},
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
