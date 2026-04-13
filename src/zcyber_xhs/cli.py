"""CLI entry point — the `zcyber` command."""

from __future__ import annotations

import os
import sys

# Fix Windows console encoding for Chinese output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click

from .config import Config
from .db import Database
from .models import Archetype, PostStatus


def _get_config() -> Config:
    return Config()


def _get_db(config: Config) -> Database:
    db = Database(config.base_dir / "zcyber_xhs.db")
    db.init()
    return db


@click.group()
def cli():
    """zcyber-xhs: Automated cybersecurity content pipeline for Xiaohongshu."""
    pass


# ── Generate ──────────────────────────────────────────────


@cli.command()
@click.option(
    "--archetype",
    "-a",
    type=click.Choice([a.value for a in Archetype]),
    default="problem_command",
    help="Content archetype to generate.",
)
@click.option("--topic", "-t", default=None, help="Specific topic slug to use.")
def generate(archetype: str, topic: str | None):
    """Generate a post for the given archetype."""
    config = _get_config()
    db = _get_db(config)

    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(config, db)
    post_id = orchestrator.run(archetype, topic_override=topic)

    if post_id:
        click.echo(f"\nDone! Post #{post_id} is in draft queue.")
    else:
        click.echo("\nFailed to generate post.")

    db.close()


# ── Queue ─────────────────────────────────────────────────


@cli.group()
def queue():
    """Manage the post draft queue."""
    pass


@queue.command("list")
@click.option(
    "--status",
    "-s",
    type=click.Choice([s.value for s in PostStatus]),
    default=None,
    help="Filter by status.",
)
@click.option("--limit", "-n", default=20, help="Max posts to show.")
def queue_list(status: str | None, limit: int):
    """List posts in the queue."""
    config = _get_config()
    db = _get_db(config)

    filter_status = PostStatus(status) if status else None
    posts = db.list_posts(status=filter_status, limit=limit)

    if not posts:
        click.echo("No posts found.")
        db.close()
        return

    click.echo(f"{'ID':>4}  {'Status':<10}  {'Archetype':<18}  {'Title'}")
    click.echo("-" * 70)
    for p in posts:
        click.echo(f"{p.id:>4}  {p.status.value:<10}  {p.archetype:<18}  {p.title or '(no title)'}")

    db.close()


@queue.command("approve")
@click.argument("post_id", type=int)
def queue_approve(post_id: int):
    """Approve a draft for publishing."""
    config = _get_config()
    db = _get_db(config)

    from .queue import DraftQueue

    q = DraftQueue(config, db)
    if q.approve(post_id):
        click.echo(f"Post #{post_id} approved.")
    else:
        click.echo(f"Post #{post_id} not found or not in draft status.")

    db.close()


@queue.command("reject")
@click.argument("post_id", type=int)
def queue_reject(post_id: int):
    """Reject a draft."""
    config = _get_config()
    db = _get_db(config)

    from .queue import DraftQueue

    q = DraftQueue(config, db)
    if q.reject(post_id):
        click.echo(f"Post #{post_id} rejected.")
    else:
        click.echo(f"Post #{post_id} not found or not in draft status.")

    db.close()


@queue.command("show")
@click.argument("post_id", type=int)
def queue_show(post_id: int):
    """Show full details of a post."""
    config = _get_config()
    db = _get_db(config)

    post = db.get_post(post_id)
    if not post:
        click.echo(f"Post #{post_id} not found.")
        db.close()
        return

    click.echo(f"ID:        {post.id}")
    click.echo(f"Status:    {post.status.value}")
    click.echo(f"Archetype: {post.archetype}")
    click.echo(f"Topic:     {post.topic_slug}")
    click.echo(f"Title:     {post.title}")
    click.echo(f"Tags:      {', '.join(post.tags)}")
    click.echo(f"Image:     {post.image_path or '(none)'}")
    click.echo(f"Created:   {post.created_at}")
    click.echo(f"\n{'-' * 50}")
    click.echo(post.body)

    db.close()


# ── Publish ───────────────────────────────────────────────


@cli.command()
@click.argument("post_id", type=int, required=False)
def publish(post_id: int | None):
    """Publish the next approved post (or a specific post by ID)."""
    config = _get_config()
    db = _get_db(config)

    from .publish import Publisher
    from .queue import DraftQueue

    if post_id:
        post = db.get_post(post_id)
        if not post:
            click.echo(f"Post #{post_id} not found.")
            db.close()
            return
        if post.status != PostStatus.APPROVED:
            click.echo(f"Post #{post_id} is '{post.status.value}', not approved.")
            db.close()
            return
    else:
        q = DraftQueue(config, db)
        post = q.next_publishable()
        if not post:
            click.echo("No publishable posts. Approve a draft first, or check rate limits.")
            db.close()
            return

    publisher = Publisher(config, db)

    # Check MCP health first
    if not publisher.health_check():
        click.echo("xiaohongshu-mcp is not reachable. Is it running?")
        db.close()
        return

    click.echo(f"Publishing post #{post.id}: {post.title}")
    try:
        url = publisher.publish(post)
        click.echo(f"Published! URL: {url}")
    except RuntimeError as e:
        click.echo(f"Failed: {e}")

    db.close()


# ── Scheduler ─────────────────────────────────────────────


@cli.command()
def run():
    """Start the scheduler (runs generation + publishing on cron)."""
    config = _get_config()

    from .scheduler import create_scheduler, print_schedule

    print_schedule(config)
    click.echo()
    click.echo("Starting scheduler... Press Ctrl+C to stop.\n")

    scheduler = create_scheduler(config)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        click.echo("\nScheduler stopped.")


@cli.command()
def schedule():
    """Show the weekly content schedule."""
    config = _get_config()

    from .scheduler import print_schedule

    print_schedule(config)


@cli.command()
def bot():
    """Start the Telegram review bot."""
    import asyncio

    config = _get_config()
    db = _get_db(config)

    from .review_bot import run_bot

    click.echo("Starting Telegram review bot...")
    click.echo("Commands: /start, /drafts, /status")
    click.echo("Press Ctrl+C to stop.\n")

    try:
        asyncio.run(run_bot(config, db))
    except (KeyboardInterrupt, SystemExit):
        click.echo("\nBot stopped.")
    finally:
        db.close()


# ── Status ────────────────────────────────────────────────


@cli.command()
def status():
    """Show pipeline status summary."""
    config = _get_config()
    db = _get_db(config)

    from .discover.topic_bank import TopicBank

    bank = TopicBank(config.base_dir / "config", db)

    drafts = len(db.list_posts(status=PostStatus.DRAFT))
    approved = len(db.list_posts(status=PostStatus.APPROVED))
    published = len(db.list_posts(status=PostStatus.PUBLISHED))
    published_today = db.count_published_today()

    click.echo("Pipeline Status")
    click.echo("-" * 40)
    click.echo(f"Drafts:           {drafts}")
    click.echo(f"Approved:         {approved}")
    click.echo(f"Published total:  {published}")
    click.echo(f"Published today:  {published_today}")
    click.echo()

    # Topic bank stats
    archetypes_with_banks = [
        "problem_command", "tool_spotlight", "everyday_panic",
        "before_after", "mythbust",
    ]
    for archetype in archetypes_with_banks:
        remaining = bank.count_remaining(archetype)
        total = len(bank.list_topics(archetype))
        click.echo(f"Topics [{archetype}]: {remaining}/{total} remaining")

    db.close()
