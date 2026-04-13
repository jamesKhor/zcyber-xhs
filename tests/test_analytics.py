"""Tests for analytics and shadowban detection."""

import tempfile

from zcyber_xhs.analytics import ShadowbanStatus, _calc_engagement_rate
from zcyber_xhs.db import Database
from zcyber_xhs.models import PostRecord, PostStatus


def _make_db() -> Database:
    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    db.init()
    return db


def _insert_published_post(db: Database, post_id_hint: int, archetype: str = "test") -> int:
    post = PostRecord(
        archetype=archetype,
        topic_slug=f"topic-{post_id_hint}",
        title=f"Title {post_id_hint}",
        body="body",
    )
    post_id = db.insert_post(post)
    db.update_post_status(post_id, PostStatus.PUBLISHED, published_url=f"https://xhs/{post_id}")
    return post_id


def test_insert_and_get_metrics():
    db = _make_db()
    post_id = _insert_published_post(db, 1)

    db.insert_metrics(post_id, views=500, likes=30, comments=10, saves=20, hours_since=24)
    metrics = db.get_latest_metrics(post_id)

    assert metrics is not None
    assert metrics["views"] == 500
    assert metrics["likes"] == 30
    assert metrics["hours_since_publish"] == 24
    db.close()


def test_metrics_returns_latest():
    db = _make_db()
    post_id = _insert_published_post(db, 1)

    db.insert_metrics(post_id, views=100, hours_since=12)
    db.insert_metrics(post_id, views=500, hours_since=24)

    metrics = db.get_latest_metrics(post_id)
    assert metrics["views"] == 500
    assert metrics["hours_since_publish"] == 24
    db.close()


def test_no_metrics_returns_none():
    db = _make_db()
    post_id = _insert_published_post(db, 1)

    metrics = db.get_latest_metrics(post_id)
    assert metrics is None
    db.close()


def test_health_event_logging():
    db = _make_db()
    db.log_health_event("test_event", "This is a test", "info")
    db.log_health_event("shadowban_detected", "Views cratered", "critical")

    events = db.get_health_events(limit=10)
    assert len(events) == 2
    assert events[0]["severity"] == "critical"  # most recent first
    db.close()


def test_engagement_rate_calculation():
    row = {
        "avg_views": 1000,
        "avg_likes": 50,
        "avg_comments": 20,
        "avg_saves": 30,
    }
    rate = _calc_engagement_rate(row)
    assert rate == 10.0  # (50+20+30)/1000 * 100


def test_engagement_rate_zero_views():
    row = {
        "avg_views": 0,
        "avg_likes": 0,
        "avg_comments": 0,
        "avg_saves": 0,
    }
    assert _calc_engagement_rate(row) == 0.0


def test_shadowban_status_dataclass():
    status = ShadowbanStatus(
        is_shadowbanned=True,
        confidence="high",
        consecutive_low=3,
        message="test",
    )
    assert status.is_shadowbanned
    assert status.confidence == "high"
    assert status.consecutive_low == 3
