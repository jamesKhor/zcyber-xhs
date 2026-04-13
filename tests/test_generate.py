"""Tests for content generation (prompt rendering, model validation)."""

from jinja2 import Template

from zcyber_xhs.models import Archetype, ImageText, PostDraft, TopicEntry


def test_post_draft_model():
    draft = PostDraft(
        archetype=Archetype.PROBLEM_COMMAND,
        title="忘记zip密码？一招搞定",
        body="测试正文内容",
        tags=["#网络安全", "#效率工具"],
        image_text=ImageText(
            headline="忘记zip密码",
            command="fcrackzip -u file.zip",
            caption="一分钟搞定",
        ),
        cta="更多威胁情报 → 主页 zcybernews",
        safety_disclaimer_needed=True,
    )
    assert draft.archetype == Archetype.PROBLEM_COMMAND
    assert draft.safety_disclaimer_needed is True
    assert len(draft.tags) == 2


def test_topic_entry_model():
    topic = TopicEntry(
        slug="zip-password",
        problem="忘记zip压缩包密码",
        tool="fcrackzip",
        command="fcrackzip -u -m 3 -c a1 -l 4-8 file.zip",
        category="password_recovery",
    )
    assert topic.slug == "zip-password"
    assert "fcrackzip" in topic.command


def test_prompt_template_rendering():
    template_text = """问题：{{ problem }}
工具：{{ tool }}
命令：{{ command }}
CTA：{{ cta }}"""

    template = Template(template_text)
    result = template.render(
        problem="忘记zip密码",
        tool="fcrackzip",
        command="fcrackzip -u file.zip",
        cta="关注zcybernews",
    )

    assert "忘记zip密码" in result
    assert "fcrackzip -u file.zip" in result
    assert "关注zcybernews" in result
