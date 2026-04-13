"""Image renderer — Playwright HTML→PNG for XHS text cards."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from ..config import Config
from ..models import PostDraft


class ImageRenderer:
    """Render post drafts into 1080x1440 PNG text cards."""

    def __init__(self, config: Config):
        self.config = config
        self.templates_dir = Path(__file__).parent / "templates"
        self.output_dir = config.base_dir / config.images.get("output_dir", "output/images")
        self.width = config.images.get("width", 1080)
        self.height = config.images.get("height", 1440)

    async def render(self, draft: PostDraft, filename: str) -> Path:
        """Render a post draft to a PNG image.

        Args:
            draft: The post draft with image_text data.
            filename: Output filename (without extension).

        Returns:
            Path to the generated PNG.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{filename}.png"

        # Load and render HTML template
        template_file = self.templates_dir / f"{draft.image_template}.html"
        if not template_file.exists():
            raise FileNotFoundError(f"Image template not found: {template_file}")

        html_template = template_file.read_text(encoding="utf-8")
        template = Template(html_template)

        html_content = template.render(
            headline=draft.image_text.headline,
            command=draft.image_text.command,
            output_preview=draft.image_text.output_preview,
            caption=draft.image_text.caption,
            cta=self.config.content.get("cta", ""),
            safety_disclaimer=(
                self.config.content.get("safety_disclaimer", "")
                if draft.safety_disclaimer_needed
                else ""
            ),
        )

        # Render with Playwright
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                viewport={"width": self.width, "height": self.height},
                device_scale_factor=2,
            )
            await page.set_content(html_content, wait_until="networkidle")
            await page.screenshot(path=str(output_path), type="png")
            await browser.close()

        return output_path

    def render_sync(self, draft: PostDraft, filename: str) -> Path:
        """Synchronous wrapper for render()."""
        import asyncio

        return asyncio.run(self.render(draft, filename))
