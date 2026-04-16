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

from pathlib import Path

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
@click.option(
    "--text-only",
    is_flag=True,
    default=False,
    help="Skip image rendering (fast mode). Use 'zcyber export' later to render.",
)
def generate(archetype: str, topic: str | None, text_only: bool):
    """Generate a post for the given archetype."""
    config = _get_config()
    db = _get_db(config)

    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(config, db)
    post_id = orchestrator.run(archetype, topic_override=topic, text_only=text_only)

    if post_id:
        click.echo(f"\nDone! Post #{post_id} is in draft queue.")
    else:
        click.echo("\nFailed to generate post.")

    db.close()


# ── Export (manual publishing helper) ─────────────────────


@cli.command()
@click.argument("post_id", type=int, required=False)
@click.option(
    "--all-approved",
    is_flag=True,
    help="Export ALL approved posts instead of a single one.",
)
def export(post_id: int | None, all_approved: bool):
    """Export post(s) to a folder ready for manual publishing to XHS.

    Creates output/manual_publish/<timestamp>_<id>/ containing:
      - The image(s)
      - post.txt with title, body, and tags ready to copy-paste

    Examples:
      zcyber export 19              # export one post
      zcyber export --all-approved  # export every approved post
    """
    import json
    import shutil
    from datetime import datetime
    from pathlib import Path

    config = _get_config()
    db = _get_db(config)

    # Resolve which posts to export
    if all_approved:
        posts = db.list_posts(status=PostStatus.APPROVED)
        if not posts:
            click.echo("No approved posts to export.")
            db.close()
            return
    elif post_id:
        single = db.get_post(post_id)
        if not single:
            click.echo(f"Post #{post_id} not found.")
            db.close()
            return
        posts = [single]
    else:
        # No args — show pending drafts and approved to help the user pick
        click.echo("Usage: zcyber export <post_id>  OR  zcyber export --all-approved\n")
        drafts = db.list_posts(status=PostStatus.DRAFT, limit=10)
        approved = db.list_posts(status=PostStatus.APPROVED, limit=10)
        if drafts:
            click.echo("Pending drafts:")
            for p in drafts:
                click.echo(f"  #{p.id} [{p.archetype}] {p.title[:50]}")
        if approved:
            click.echo("Approved (ready to publish):")
            for p in approved:
                click.echo(f"  #{p.id} [{p.archetype}] {p.title[:50]}")
        if not drafts and not approved:
            click.echo("No posts in queue. Run `zcyber generate` first.")
        db.close()
        return

    # Create export root
    export_root = config.base_dir / "output" / "manual_publish"
    export_root.mkdir(parents=True, exist_ok=True)

    for post in posts:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{ts}_post{post.id}_{post.archetype}"
        dest = export_root / folder_name
        dest.mkdir(exist_ok=True)

        # Copy image(s)
        image_count = 0
        if post.image_path:
            paths = [post.image_path]
            if post.image_path.startswith("["):
                try:
                    paths = json.loads(post.image_path)
                except json.JSONDecodeError:
                    pass

            for idx, src in enumerate(paths, start=1):
                src_path = Path(src)
                if not src_path.exists():
                    continue
                if len(paths) > 1:
                    new_name = f"image_{idx:02d}{src_path.suffix}"
                else:
                    new_name = f"image{src_path.suffix}"
                shutil.copy2(src_path, dest / new_name)
                image_count += 1

        # Write copy-paste friendly text file
        tags = post.tags or []
        tags_formatted = " ".join(
            t if t.startswith("#") else f"#{t}" for t in tags
        )

        text_lines = [
            "=" * 60,
            f"POST #{post.id} — {post.archetype}",
            "=" * 60,
            "",
            "TITLE (copy this into the XHS title field, max 20 chars):",
            "-" * 60,
            post.title or "",
            "",
            "BODY (copy this into the XHS content area):",
            "-" * 60,
            post.body or "",
            "",
            "TAGS (type these one by one in XHS):",
            "-" * 60,
            tags_formatted,
            "",
            "=" * 60,
            f"IMAGES: {image_count} file(s) in this folder",
            "=" * 60,
        ]
        (dest / "post.txt").write_text(
            "\n".join(text_lines), encoding="utf-8"
        )

        click.echo(f"Exported #{post.id} → {dest}")

    click.echo("\nDone. Open the folder(s) in File Explorer:")
    click.echo(f"  {export_root}")
    click.echo("\nSend the whole folder to your phone via WeChat "
               "(文件传输助手) and publish manually in the XHS app.")

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
    config = _get_config()
    db = Database(config.base_dir / "zcyber_xhs.db", cross_thread=True)
    db.init()

    from .review_bot import run_bot_sync

    click.echo("Starting Telegram review bot...")
    click.echo("Commands: /start, /drafts, /status")
    click.echo("Press Ctrl+C to stop.\n")

    try:
        run_bot_sync(config, db)
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
        "problem_command", "everyday_panic", "mythbust",
        "real_story", "rank_war", "hacker_pov",
    ]
    for archetype in archetypes_with_banks:
        remaining = bank.count_remaining(archetype)
        total = len(bank.list_topics(archetype))
        click.echo(f"Topics [{archetype}]: {remaining}/{total} remaining")

    db.close()


# ── Analytics ────────────────────────────────────────────


@cli.group()
def analytics():
    """View analytics and check account health."""
    pass


@analytics.command("poll")
def analytics_poll():
    """Poll metrics for all published posts."""
    config = _get_config()
    db = _get_db(config)

    from .analytics import Analytics

    a = Analytics(config, db)
    updated = a.poll_all_published()
    click.echo(f"Updated metrics for {updated} posts.")
    db.close()


@analytics.command("check")
def analytics_check():
    """Check for shadowban indicators."""
    config = _get_config()
    db = _get_db(config)

    from .analytics import Analytics

    a = Analytics(config, db)
    status = a.check_shadowban()

    if status.is_shadowbanned:
        click.echo(f"[CRITICAL] {status.message}")
    elif status.confidence == "warning":
        click.echo(f"[WARNING] {status.message}")
    else:
        click.echo(f"[OK] {status.message}")

    db.close()


@analytics.command("performance")
def analytics_performance():
    """Show archetype performance rankings."""
    config = _get_config()
    db = _get_db(config)

    from .analytics import Analytics

    a = Analytics(config, db)
    perf = a.get_archetype_performance()

    if not perf:
        click.echo("No performance data yet. Metrics are polled after posts are published.")
        db.close()
        return

    click.echo(f"{'Archetype':<20} {'Posts':>5} {'Views':>7} {'Likes':>6} "
               f"{'Comments':>8} {'Saves':>6} {'Eng%':>6}")
    click.echo("-" * 65)
    for arch, data in sorted(perf.items(), key=lambda x: x[1]["avg_views"], reverse=True):
        click.echo(
            f"{arch:<20} {data['post_count']:>5} {data['avg_views']:>7} "
            f"{data['avg_likes']:>6} {data['avg_comments']:>8} "
            f"{data['avg_saves']:>6} {data['engagement_rate']:>5.1f}%"
        )

    db.close()


@cli.command()
def gui():
    """Launch the local web GUI (opens in browser at localhost:8501)."""
    import subprocess
    subprocess.run([sys.executable, "-m", "streamlit", "run",
                   str(Path(__file__).parent / "gui.py"), "--server.headless", "true"])


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8080, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Enable hot-reload (dev mode)")
def web(host: str, port: int, reload: bool):
    """Launch the FastAPI web UI (http://localhost:8080).

    Replaces the old Streamlit GUI with a proper web application.
    """
    import uvicorn
    click.echo(f"Starting ZCyber web UI at http://{host}:{port}")
    uvicorn.run("zcyber_xhs.web:app", host=host, port=port, reload=reload)


@analytics.command("health")
def analytics_health():
    """Show recent pipeline health events."""
    config = _get_config()
    db = _get_db(config)

    events = db.get_health_events(limit=20)
    if not events:
        click.echo("No health events logged.")
        db.close()
        return

    for e in events:
        sev = e["severity"].upper()
        click.echo(f"[{sev}] {e['created_at']} - {e['event_type']}: {e['message']}")

    db.close()
