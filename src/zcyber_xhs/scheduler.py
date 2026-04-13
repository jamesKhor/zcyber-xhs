"""APScheduler-based cron scheduler for the content pipeline."""

from __future__ import annotations

import logging
from datetime import datetime

import click
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import Database

logger = logging.getLogger("zcyber.scheduler")

# Day of week: 0=Mon ... 6=Sun
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _get_archetype_for_day(config: Config, day_of_week: int) -> str:
    """Get the archetype assigned to a day of the week (0=Mon)."""
    rotation = config.schedule.get("rotation", {})
    return rotation.get(day_of_week, "problem_command")


def _generation_job(config_path: str) -> None:
    """Scheduled job: generate content for today's archetype.

    Takes config_path as string so APScheduler can serialize it.
    """
    config = Config(config_path)
    db = Database(config.base_dir / "zcyber_xhs.db")
    db.init()

    day = datetime.now().weekday()
    archetype = _get_archetype_for_day(config, day)
    day_name = DAY_NAMES[day]
    logger.info(f"[Gen] {day_name}: generating {archetype}")
    click.echo(f"[Scheduler] {day_name}: generating {archetype}")

    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(config, db)
    post_id = orchestrator.run(archetype)

    if post_id:
        logger.info(f"[Gen] Post {post_id} created")
        # Notify via Telegram if configured
        _notify_new_draft(config, db, post_id)
    else:
        logger.warning("[Gen] No topic available, skipping")

    db.close()


def _publish_job(config_path: str) -> None:
    """Scheduled job: publish the next approved post."""
    config = Config(config_path)
    db = Database(config.base_dir / "zcyber_xhs.db")
    db.init()

    from .publish import Publisher
    from .queue import DraftQueue

    queue = DraftQueue(config, db)
    post = queue.next_publishable()

    if not post:
        logger.info("[Pub] No publishable posts")
        db.close()
        return

    publisher = Publisher(config, db)
    try:
        url = publisher.publish(post)
        logger.info(f"[Pub] Published post {post.id}: {url}")
        click.echo(f"[Scheduler] Published post {post.id}: {url}")
    except RuntimeError as e:
        logger.error(f"[Pub] Failed: {e}")
        click.echo(f"[Scheduler] Publish failed: {e}")

    db.close()


def _notify_new_draft(config: Config, db: Database, post_id: int) -> None:
    """Send Telegram notification for a new draft (if configured)."""
    import os

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    try:
        from .review_bot import send_draft_preview

        post = db.get_post(post_id)
        if post:
            send_draft_preview(token, chat_id, post)
    except Exception as e:
        logger.warning(f"[Telegram] Notification failed: {e}")


def create_scheduler(config: Config) -> BlockingScheduler:
    """Create and configure the APScheduler instance with SQLite persistence."""
    db_url = f"sqlite:///{config.base_dir / 'scheduler_jobs.db'}"

    jobstores = {
        "default": SQLAlchemyJobStore(url=db_url),
    }

    scheduler = BlockingScheduler(jobstores=jobstores)

    gen_hour = config.schedule.get("generate_hour", 8)
    pub_hour = config.schedule.get("publish_hour", 12)
    config_path = str(config.base_dir / "config" / "config.yaml")

    # Daily generation job — runs every day at gen_hour
    scheduler.add_job(
        _generation_job,
        CronTrigger(hour=gen_hour, minute=0),
        args=[config_path],
        id="daily_generation",
        name="Daily content generation",
        replace_existing=True,
    )

    # Midday publish job
    scheduler.add_job(
        _publish_job,
        CronTrigger(hour=pub_hour, minute=0),
        args=[config_path],
        id="midday_publish",
        name="Midday publish drain",
        replace_existing=True,
    )

    # Afternoon publish job (second window)
    afternoon_hour = min(pub_hour + 6, 23)
    scheduler.add_job(
        _publish_job,
        CronTrigger(hour=afternoon_hour, minute=30),
        args=[config_path],
        id="afternoon_publish",
        name="Afternoon publish drain",
        replace_existing=True,
    )

    return scheduler


def print_schedule(config: Config) -> None:
    """Print the weekly schedule to stdout."""
    rotation = config.schedule.get("rotation", {})
    gen_hour = config.schedule.get("generate_hour", 8)
    pub_hour = config.schedule.get("publish_hour", 12)

    click.echo("Weekly Schedule")
    click.echo("-" * 45)
    for day_num in range(7):
        archetype = rotation.get(day_num, "problem_command")
        click.echo(f"  {DAY_NAMES[day_num]:<4}  {archetype}")
    click.echo()
    click.echo(f"Generation: daily at {gen_hour:02d}:00")
    click.echo(f"Publish:    {pub_hour:02d}:00 and {min(pub_hour+6, 23):02d}:30")
