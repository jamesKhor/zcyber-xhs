"""APScheduler-based cron scheduler for the content pipeline."""

from __future__ import annotations

import click
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import Database
from .orchestrator import Orchestrator
from .publish import Publisher
from .queue import DraftQueue


def _get_archetype_for_day(config: Config, day_of_week: int) -> str:
    """Get the archetype assigned to a day of the week (0=Mon)."""
    rotation = config.schedule.get("rotation", {})
    return rotation.get(day_of_week, "problem_command")


def _generation_job(config: Config, db: Database) -> None:
    """Scheduled job: generate content for today's archetype."""
    from datetime import datetime

    day = datetime.now().weekday()
    archetype = _get_archetype_for_day(config, day)
    click.echo(f"[Scheduler] Generating: {archetype} (day={day})")

    orchestrator = Orchestrator(config, db)
    post_id = orchestrator.run(archetype)

    if post_id:
        click.echo(f"[Scheduler] Generated post {post_id}")
    else:
        click.echo("[Scheduler] No topic available, skipping")


def _publish_job(config: Config, db: Database) -> None:
    """Scheduled job: publish the next approved post."""
    queue = DraftQueue(config, db)
    post = queue.next_publishable()

    if not post:
        click.echo("[Scheduler] No publishable posts in queue")
        return

    publisher = Publisher(config, db)
    try:
        url = publisher.publish(post)
        click.echo(f"[Scheduler] Published post {post.id}: {url}")
    except RuntimeError as e:
        click.echo(f"[Scheduler] Publish failed: {e}")


def create_scheduler(config: Config, db: Database) -> BlockingScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = BlockingScheduler()

    gen_hour = config.schedule.get("generate_hour", 8)
    pub_hour = config.schedule.get("publish_hour", 12)

    # Daily generation job
    scheduler.add_job(
        _generation_job,
        CronTrigger(hour=gen_hour, minute=0),
        args=[config, db],
        id="daily_generation",
        name="Daily content generation",
        replace_existing=True,
    )

    # Daily publish job (drain approved queue)
    scheduler.add_job(
        _publish_job,
        CronTrigger(hour=pub_hour, minute=0),
        args=[config, db],
        id="daily_publish",
        name="Daily publish drain",
        replace_existing=True,
    )

    # Second publish window (afternoon)
    scheduler.add_job(
        _publish_job,
        CronTrigger(hour=pub_hour + 6, minute=30),
        args=[config, db],
        id="afternoon_publish",
        name="Afternoon publish drain",
        replace_existing=True,
    )

    return scheduler
