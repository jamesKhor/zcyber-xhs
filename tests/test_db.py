"""Tests for the database module."""

import tempfile

from zcyber_xhs.db import Database
from zcyber_xhs.models import PostRecord, PostStatus


def _make_db() -> Database:
    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    db.init()
    return db


def test_insert_and_get_post():
    db = _make_db()
    post = PostRecord(
        archetype="problem_command",
        topic_slug="zip-password",
        title="Test title",
        body="Test body",
        tags=["#test"],
    )
    post_id = db.insert_post(post)
    assert post_id > 0

    fetched = db.get_post(post_id)
    assert fetched is not None
    assert fetched.title == "Test title"
    assert fetched.tags == ["#test"]
    assert fetched.status == PostStatus.DRAFT
    db.close()


def test_update_status():
    db = _make_db()
    post = PostRecord(
        archetype="problem_command",
        topic_slug="test",
        title="T",
        body="B",
    )
    post_id = db.insert_post(post)
    db.update_post_status(post_id, PostStatus.APPROVED)

    fetched = db.get_post(post_id)
    assert fetched.status == PostStatus.APPROVED
    db.close()


def test_topic_dedup():
    db = _make_db()
    assert not db.is_topic_used("problem_command", "zip-password")

    db.mark_topic_used("problem_command", "zip-password")
    assert db.is_topic_used("problem_command", "zip-password")
    assert not db.is_topic_used("problem_command", "other-topic")
    db.close()


def test_list_posts_by_status():
    db = _make_db()
    for i in range(3):
        db.insert_post(PostRecord(
            archetype="test",
            topic_slug=f"topic-{i}",
            title=f"Title {i}",
            body="body",
        ))

    # Approve one
    db.update_post_status(1, PostStatus.APPROVED)

    drafts = db.list_posts(status=PostStatus.DRAFT)
    assert len(drafts) == 2

    approved = db.list_posts(status=PostStatus.APPROVED)
    assert len(approved) == 1
    db.close()


def test_count_published_today():
    db = _make_db()
    assert db.count_published_today() == 0

    post = PostRecord(
        archetype="test", topic_slug="t", title="T", body="B"
    )
    post_id = db.insert_post(post)
    db.update_post_status(post_id, PostStatus.PUBLISHED, published_url="https://example.com")

    assert db.count_published_today() == 1
    db.close()
