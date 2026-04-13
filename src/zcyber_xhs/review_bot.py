"""Telegram review bot — sends draft previews with inline approve/reject."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from .config import Config
from .db import Database
from .models import PostRecord, PostStatus
from .queue import DraftQueue

logger = logging.getLogger("zcyber.telegram")


def send_draft_preview(token: str, chat_id: str, post: PostRecord) -> None:
    """Send a draft preview to Telegram with inline approve/reject buttons."""
    asyncio.run(_send_preview_async(token, chat_id, post))


async def _send_preview_async(token: str, chat_id: str, post: PostRecord) -> None:
    """Async implementation of draft preview sending."""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    bot = Bot(token=token)

    # Build preview text
    text = (
        f"*NEW DRAFT #{post.id}*\n"
        f"Archetype: `{post.archetype}`\n"
        f"Topic: `{post.topic_slug}`\n\n"
        f"*{_escape_md(post.title)}*\n\n"
        f"{_truncate(_escape_md(post.body), 500)}\n\n"
        f"Tags: {', '.join(post.tags[:5])}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"approve_{post.id}"),
            InlineKeyboardButton("Reject", callback_data=f"reject_{post.id}"),
        ],
        [
            InlineKeyboardButton("Regenerate", callback_data=f"regen_{post.id}"),
        ],
    ])

    # Send image first if available
    image_paths = _resolve_image_paths(post.image_path)
    if image_paths:
        first_image = image_paths[0]
        try:
            with open(first_image, "rb") as photo:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=f"Draft #{post.id}: {post.title[:100]}",
                )
        except Exception as e:
            logger.warning(f"Failed to send photo: {e}")

    # Send text with inline buttons
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


def _resolve_image_paths(image_path_str: str | None) -> list[str]:
    """Parse image path(s) from single path or JSON array."""
    if not image_path_str:
        return []

    if image_path_str.startswith("["):
        try:
            paths = json.loads(image_path_str)
            return [p for p in paths if Path(p).exists()]
        except json.JSONDecodeError:
            pass

    if Path(image_path_str).exists():
        return [image_path_str]

    return []


def _escape_md(text: str) -> str:
    """Escape Markdown special characters for Telegram."""
    for ch in ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}"]:
        text = text.replace(ch, f"\\{ch}")
    return text


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


async def run_bot(config: Config, db: Database) -> None:
    """Run the Telegram bot with callback query handlers."""
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
    )

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    queue = DraftQueue(config, db)

    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "zcyber-xhs review bot\n\n"
            "Commands:\n"
            "/drafts - List pending drafts\n"
            "/status - Pipeline status\n\n"
            "I'll send you previews when new posts are generated."
        )

    async def drafts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        drafts = queue.list_drafts(limit=10)
        if not drafts:
            await update.message.reply_text("No pending drafts.")
            return

        lines = ["*Pending Drafts:*\n"]
        for d in drafts:
            lines.append(f"#{d.id} \\[{d.archetype}\\] {_escape_md(d.title or '(no title)')}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        draft_count = len(db.list_posts(status=PostStatus.DRAFT))
        approved_count = len(db.list_posts(status=PostStatus.APPROVED))
        published_count = len(db.list_posts(status=PostStatus.PUBLISHED))
        today_count = db.count_published_today()

        text = (
            f"*Pipeline Status*\n\n"
            f"Drafts: {draft_count}\n"
            f"Approved: {approved_count}\n"
            f"Published: {published_count}\n"
            f"Today: {today_count}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def callback_handler(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        data = query.data
        if data.startswith("approve_"):
            post_id = int(data.split("_")[1])
            if queue.approve(post_id):
                await query.edit_message_text(
                    f"Post #{post_id} APPROVED and queued for publishing."
                )
            else:
                await query.edit_message_text(
                    f"Post #{post_id} could not be approved (not in draft status)."
                )

        elif data.startswith("reject_"):
            post_id = int(data.split("_")[1])
            if queue.reject(post_id):
                await query.edit_message_text(f"Post #{post_id} REJECTED.")
            else:
                await query.edit_message_text(
                    f"Post #{post_id} could not be rejected."
                )

        elif data.startswith("reject_") or data.startswith("regen_"):
            post_id = int(data.split("_")[1])
            post = db.get_post(post_id)
            if not post:
                await query.edit_message_text(f"Post #{post_id} not found.")
                return

            queue.reject(post_id)
            is_regen = data.startswith("regen_")

            if is_regen:
                await query.edit_message_text(
                    f"Post #{post_id} rejected. Regenerating..."
                )
                # Auto-regenerate same archetype
                try:
                    from .orchestrator import Orchestrator

                    orchestrator = Orchestrator(config, db)
                    new_id = orchestrator.run(post.archetype)
                    if new_id:
                        new_post = db.get_post(new_id)
                        if new_post:
                            chat_id = str(query.message.chat_id)
                            await _send_preview_async(token, chat_id, new_post)
                    else:
                        await query.message.reply_text(
                            f"No topics left for {post.archetype}."
                        )
                except Exception as e:
                    await query.message.reply_text(f"Regen failed: {e}")
            else:
                await query.edit_message_text(f"Post #{post_id} REJECTED.")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("drafts", drafts_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Telegram bot started")
    await app.run_polling()
