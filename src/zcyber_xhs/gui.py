"""Streamlit local GUI for the zcyber-xhs content pipeline.

Run with:
    streamlit run src/zcyber_xhs/gui.py
or:
    zcyber gui
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ZCyber XHS",
    page_icon="🔐",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the project root (two levels above this file)."""
    return Path(__file__).parent.parent.parent


def _get_config():
    """Load Config — cached as a resource so it is only read once."""
    # Import here to avoid module-level side-effects at import time
    sys.path.insert(0, str(_project_root() / "src"))
    from zcyber_xhs.config import Config  # noqa: PLC0415
    return Config()


@st.cache_resource
def _cached_config():
    return _get_config()


def _get_db():
    """Return a fresh Database instance, already initialised."""
    from zcyber_xhs.db import Database  # noqa: PLC0415
    config = _cached_config()
    db = Database(config.base_dir / "zcyber_xhs.db")
    db.init()
    return db


# ---------------------------------------------------------------------------
# Archetype metadata
# ---------------------------------------------------------------------------

ARCHETYPES = [
    ("problem_command", "命令技巧"),
    ("real_story",      "真实事件"),   # Tue
    ("everyday_panic",  "日常惊魂"),
    ("rank_war",        "观点对决"),   # Thu
    ("mythbust",        "辟谣"),
    ("news_hook",       "时事钩子"),
    ("hacker_pov",      "黑客视角"),   # Sun — replaces ctf
    # Legacy archetypes — kept for historical posts in DB
    ("tool_spotlight",  "工具推荐 (旧)"),
    ("before_after",    "前后对比 (旧)"),
    ("ctf",             "CTF挑战 (旧)"),
]

BANK_ARCHETYPES = [
    "problem_command", "real_story", "everyday_panic",
    "rank_war", "mythbust", "hacker_pov",
    # Legacy kept for reruns
    "tool_spotlight", "before_after",
]

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _resolve_image_path(image_path: str | None) -> str | None:
    """Return the first resolvable image path from a plain string or JSON array."""
    if not image_path:
        return None
    if image_path.startswith("["):
        try:
            paths = json.loads(image_path)
            if paths:
                return str(paths[0])
        except (json.JSONDecodeError, IndexError):
            pass
        return None
    return image_path


def _status_badge(status: str) -> str:
    mapping = {
        "draft": "🟡 draft",
        "approved": "🟢 approved",
        "published": "🔵 published",
        "rejected": "🔴 rejected",
        "failed": "⚫ failed",
    }
    return mapping.get(status, status)


# ---------------------------------------------------------------------------
# Page 1 — Dashboard
# ---------------------------------------------------------------------------

def page_dashboard():
    st.title("📊 Dashboard")

    if st.button("🔄 Refresh"):
        st.rerun()

    try:
        from zcyber_xhs.discover.topic_bank import TopicBank  # noqa: PLC0415
        from zcyber_xhs.models import PostStatus  # noqa: PLC0415

        db = _get_db()
        config = _cached_config()

        drafts_count = len(db.list_posts(status=PostStatus.DRAFT))
        approved_count = len(db.list_posts(status=PostStatus.APPROVED))
        published_count = len(db.list_posts(status=PostStatus.PUBLISHED))

        # Topics remaining across all bank archetypes
        bank = TopicBank(config.base_dir / "config", db)
        topics_remaining = sum(bank.count_remaining(a) for a in BANK_ARCHETYPES)

        db.close()
    except Exception as e:
        st.error(f"Failed to load dashboard data: {e}")
        return

    # Metric cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Drafts", drafts_count)
    col2.metric("Approved", approved_count)
    col3.metric("Published", published_count)
    col4.metric("Topics Remaining", topics_remaining)

    st.divider()

    # Recent posts table
    st.subheader("Recent Posts")
    try:
        db = _get_db()
        try:
            posts = db.list_posts(limit=10)
        finally:
            db.close()
    except Exception as e:
        st.error(f"Failed to load posts: {e}")
        return

    if not posts:
        st.info("No posts yet — go to the Generate tab to create your first post.")
        return

    rows = []
    for p in posts:
        rows.append({
            "ID": p.id,
            "Archetype": p.archetype,
            "Status": _status_badge(p.status.value),
            "Title": (p.title or "")[:40],
            "Created": str(p.created_at)[:16] if p.created_at else "",
        })

    st.dataframe(rows, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Page 2 — Generate
# ---------------------------------------------------------------------------

def page_generate():
    st.title("⚡ Generate")

    col_arch, col_opts = st.columns([2, 1])

    with col_arch:
        # Engagement guide — helps pick the right archetype
        ENGAGEMENT = {
            # ── Active archetypes (current weekly rotation) ──────────────
            "problem_command": (
                "🔥", "🔥",
                "Technical — '想要下期？' or self-check prompt drives saves",
            ),
            "real_story": (
                "🔥🔥🔥", "🔥🔥🔥",
                "Personal breach story → '我朋友也遇到过!' + saves as warning",
            ),
            "everyday_panic": (
                "🔥🔥🔥", "🔥🔥🔥",
                "Relatable fear → '这不就是我！' + tag 朋友 instinct",
            ),
            "rank_war": (
                "🔥🔥🔥", "🔥🔥🔥",
                "VS debate → 'comment which side' drives heated discussion",
            ),
            "mythbust": (
                "🔥🔥🔥", "🔥🔥🔥",
                "'Wait really?!' + tag others to win arguments",
            ),
            "news_hook": (
                "🔥🔥", "🔥",
                "Opinion bait — '你怎么看这件事？' + funnel to zcybernews",
            ),
            "hacker_pov": (
                "🔥🔥🔥", "🔥🔥🔥",
                "POV immersion → '如果是我会怎么做' + saves for future reference",
            ),
            # ── Legacy archetypes (kept for historical posts) ─────────────
            "tool_spotlight": (
                "🔥", "🔥",
                "(旧) Moderate — 'have you used this?' works",
            ),
            "before_after": (
                "🔥🔥", "🔥🔥",
                "(旧) 'Which one are you?' → self-identify",
            ),
            "ctf": (
                "🔥🔥", "🔥",
                "(旧) People post their answer — replaced by hacker_pov",
            ),
        }

        expander_label = "💡 Engagement guide — which archetype gets most comments & tags?"
        with st.expander(expander_label, expanded=False):
            rows = []
            for arch, label in ARCHETYPES:
                cmts, tags, why = ENGAGEMENT.get(arch, ("", "", ""))
                rows.append({
                    "Archetype": arch,
                    "Comments": cmts,
                    "Tags": tags,
                    "Why it works": why,
                })
            st.dataframe(rows, width="stretch", hide_index=True)

        archetype_labels = [
            f"{a} — {label}  {ENGAGEMENT.get(a, ('','',''))[0]} comments"
            for a, label in ARCHETYPES
        ]
        selected_idx = st.radio(
            "Archetype",
            options=range(len(ARCHETYPES)),
            format_func=lambda i: archetype_labels[i],
            horizontal=False,
        )
        selected_archetype = ARCHETYPES[selected_idx][0]

    with col_opts:
        st.markdown("**Options**")
        count = int(st.number_input(
            "How many articles?",
            min_value=1, max_value=5, value=1, step=1,
            help="Generate multiple text drafts at once, pick the best, then render images.",
        ))
        # When generating more than 1, always skip images — user picks first, renders after
        if count > 1:
            text_only = True
            st.toggle(
                "Text only (fast — pick first, render later)",
                value=True, disabled=True,
                help="Forced ON for batch: generates text fast, you pick which to render.",
            )
        else:
            text_only = st.toggle(
                "Text only (fast)",
                value=False,
                help="Skip image rendering now. Render later from Review Queue.",
            )
        topic_override = st.text_input(
            "Topic override (optional)",
            placeholder="Leave blank to auto-pick",
        )

    st.divider()

    if st.button("🚀 Generate", type="primary"):
        _run_batch_generation(
            selected_archetype,
            topic_override.strip() or None,
            count=count,
            text_only=text_only,
        )

    # Show results stored in session state
    _display_batch_results()


def _run_batch_generation(
    archetype: str,
    topic_override: str | None,
    count: int,
    text_only: bool,
):
    """Generate 1-N posts in parallel and store all IDs in session state.

    For bank archetypes (problem_command, everyday_panic, etc.) we pre-pick
    all N topics atomically in the main thread before spinning up workers —
    this prevents two threads from racing on pick_topic() and picking the
    same unused topic twice.

    For news_hook and ctf the orchestrator handles topic selection internally
    so we just pass None and let N threads run simultaneously.
    """
    try:
        from zcyber_xhs.discover.topic_bank import TopicBank  # noqa: PLC0415
        from zcyber_xhs.orchestrator import Orchestrator  # noqa: PLC0415

        config = _cached_config()

        # ── Pre-pick topics (main thread, atomic) ──────────────────────────
        if topic_override:
            # Same explicit override for every worker
            topics_to_use: list[str | None] = [topic_override] * count
        elif archetype in BANK_ARCHETYPES:
            db = _get_db()
            try:
                bank = TopicBank(config.base_dir / "config", db)
                picked = bank.pick_n_topics(archetype, count)
            finally:
                db.close()

            if not picked:
                # Bank exhausted — let orchestrator use LLM dynamic generation
                st.info(
                    f"YAML bank for **{archetype}** is exhausted. "
                    "Generating fresh topics via AI — this may take a moment."
                )
                topics_to_use = [None] * count
            else:
                actual = len(picked)
                if actual < count:
                    st.warning(
                        f"Only {actual} unused topics available in bank — "
                        f"generating {actual} from bank + {count - actual} via AI."
                    )
                # Pass slug as override so orchestrator skips its own pick_topic()
                topics_to_use = [t.slug for t in picked] + [None] * (count - actual)
        else:
            # news_hook / ctf — topics are self-managed inside orchestrator
            topics_to_use = [None] * count

        # ── Worker: each thread gets its own DB connection ─────────────────
        def _generate_in_thread(arch: str, topic: str | None, text_only_flag: bool) -> int | None:
            db = _get_db()
            try:
                return Orchestrator(config, db).run(arch, topic, text_only_flag)
            finally:
                db.close()

        # ── Parallel dispatch ───────────────────────────────────────────────
        new_ids: list[int] = []
        errors: list[str] = []

        label = f"Generating {count} article(s) in parallel..." if count > 1 else "Generating..."
        progress = st.progress(0, text=label)

        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            future_map = {
                pool.submit(_generate_in_thread, archetype, t, text_only): idx
                for idx, t in enumerate(topics_to_use)
            }
            completed = 0
            # as_completed yields each future as soon as it finishes
            for future in concurrent.futures.as_completed(future_map, timeout=180):
                completed += 1
                progress.progress(
                    completed / count,
                    text=f"Done {completed}/{count} — waiting for remaining...",
                )
                try:
                    post_id = future.result()
                    if post_id:
                        new_ids.append(post_id)
                    else:
                        errors.append(f"Article {future_map[future] + 1}: generator returned no ID")
                except Exception as exc:
                    msg = str(exc) or type(exc).__name__
                    errors.append(f"Article {future_map[future] + 1}: {msg}")

        progress.empty()

        for err in errors:
            st.warning(err)

        if new_ids:
            st.session_state["batch_post_ids"] = new_ids
            st.session_state["batch_actions"] = {}
            st.rerun()
        else:
            st.error("All generations failed — check the terminal for details.")

    except concurrent.futures.TimeoutError:
        st.error(
            "⏱️ Generation timed out (>3 min) — DeepSeek may be overloaded. "
            "Try again or reduce count."
        )
    except Exception as e:
        msg = str(e) or type(e).__name__
        st.error(f"Generation error: {msg}")


def _display_batch_results():
    """Show all generated posts from this batch as selectable cards."""
    post_ids: list[int] = st.session_state.get("batch_post_ids", [])
    if not post_ids:
        return

    try:
        db = _get_db()
        posts = [db.get_post(pid) for pid in post_ids]
        db.close()
    except Exception as e:
        st.error(f"Failed to load posts: {e}")
        return

    posts = [p for p in posts if p]
    if not posts:
        return

    st.divider()
    _heading = (
        "Generated Post"
        if len(posts) == 1
        else f"{len(posts)} Generated Posts — pick the ones you like"
    )
    st.subheader(_heading)

    # Show deferred render result message if any
    render_msg = st.session_state.pop("batch_render_msg", None)
    if render_msg:
        if render_msg["ok"]:
            st.success(f"🖼️ Rendered {render_msg['ok']} image(s) successfully.")
        if render_msg["failed"]:
            st.error(f"{render_msg['failed']} image(s) failed to render.")

    actions: dict = st.session_state.get("batch_actions", {})

    for post in posts:
        action_taken = actions.get(post.id)
        with st.container(border=True):
            left, right = st.columns([3, 2])

            with left:
                st.subheader(post.title or "(no title)")
                st.markdown(post.body or "")
                tags_str = "  ".join(
                    t if t.startswith("#") else f"#{t}" for t in (post.tags or [])
                )
                if tags_str:
                    st.code(tags_str, language=None)
                st.caption(
                    f"#{post.id} · **{post.archetype}** · "
                    f"{_status_badge(post.status.value)}"
                    + (" · 🖼️ image ready" if post.image_path else " · 📄 text only")
                )

            with right:
                img_path = _resolve_image_path(post.image_path)
                if img_path and Path(img_path).exists():
                    st.image(img_path, width="stretch")
                else:
                    st.caption("No image yet")

            if action_taken == "approved":
                st.success(f"✅ Approved — post #{post.id} is in the export queue.")
            elif action_taken == "rejected":
                st.warning("❌ Rejected.")
            elif action_taken == "rendered":
                st.success(f"🖼️ Image rendered for post #{post.id}. Refresh to preview.")
            elif action_taken == "render_failed":
                st.error(f"🖼️ Image rendering failed for post #{post.id}.")
            elif post.status.value == "draft":
                btn1, btn2, btn3, _ = st.columns([1, 1, 1.5, 3])
                with btn1:
                    if st.button("✅ Approve", key=f"bgen_app_{post.id}"):
                        _approve_post(post.id, origin="batch")
                        actions[post.id] = "approved"
                        st.session_state["batch_actions"] = actions
                        st.rerun()
                with btn2:
                    if st.button("❌ Reject", key=f"bgen_rej_{post.id}"):
                        _reject_post(post.id, origin="batch")
                        actions[post.id] = "rejected"
                        st.session_state["batch_actions"] = actions
                        st.rerun()
                with btn3:
                    if not post.image_path:
                        if st.button("🖼️ Render Image", key=f"bgen_img_{post.id}"):
                            ok = _render_image(post.id)
                            actions[post.id] = "rendered" if ok else "render_failed"
                            st.session_state["batch_actions"] = actions
                            st.rerun()
            else:
                st.info(f"Post is already **{post.status.value}**.")

    st.divider()

    # Collect IDs of draft posts that still need images
    unrendered = [
        p.id for p in posts
        if p and p.status.value == "draft" and not p.image_path
        and actions.get(p.id) not in ("approved", "rejected")
    ]
    if unrendered:
        if st.button(
            f"🖼️ Render All Unrendered ({len(unrendered)}) — one browser session",
            type="secondary",
        ):
            _render_images_batch(unrendered, actions)

    if st.button("🗑️ Clear results"):
        st.session_state.pop("batch_post_ids", None)
        st.session_state.pop("batch_actions", None)
        st.rerun()


def _render_image(post_id: int, force: bool = False) -> bool:
    """Trigger image rendering for a draft. Returns True on success.

    Args:
        force: If True, re-render even if an image already exists.
    """
    try:
        from zcyber_xhs.orchestrator import Orchestrator  # noqa: PLC0415

        config = _cached_config()

        def _render_in_thread(pid, f):
            db = _get_db()
            try:
                return Orchestrator(config, db).render_image_for_post(pid, force=f)
            finally:
                db.close()

        label = (
            f"Re-rendering image for post #{post_id}..."
            if force
            else f"Rendering image for post #{post_id}..."
        )
        with st.spinner(label):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_render_in_thread, post_id, force).result(timeout=120)

        if not result:
            st.error(f"Image rendering failed for post #{post_id}.")
            return False
        return True
    except Exception as e:
        st.error(f"Render error: {e}")
        return False


def _batch_rerender(post_ids: list[int]) -> None:
    """Force re-render images for a list of posts (batch, one browser session)."""
    try:
        from zcyber_xhs.orchestrator import Orchestrator  # noqa: PLC0415

        config = _cached_config()

        def _in_thread(ids):
            db = _get_db()
            try:
                orch = Orchestrator(config, db)
                results = {}
                for pid in ids:
                    path = orch.render_image_for_post(pid, force=True)
                    if path:
                        results[pid] = path
                return results
            finally:
                db.close()

        with st.spinner(f"Re-rendering {len(post_ids)} image(s) with latest templates..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(_in_thread, post_ids).result(timeout=300)

        ok = len(results)
        failed = len(post_ids) - ok
        if ok:
            st.toast(f"Re-rendered {ok} image(s).", icon="🖼️")
        if failed:
            st.warning(f"{failed} image(s) failed.")
        st.rerun()
    except Exception as e:
        st.error(f"Batch re-render error: {e}")


def _render_images_batch(post_ids: list[int], actions: dict) -> None:
    """Render images for multiple posts in a single Chromium session."""
    try:
        from zcyber_xhs.orchestrator import Orchestrator  # noqa: PLC0415

        config = _cached_config()

        def _batch_in_thread(ids):
            db = _get_db()
            try:
                return Orchestrator(config, db).render_images_for_posts(ids)
            finally:
                db.close()

        with st.spinner(f"Rendering {len(post_ids)} images in one browser session..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(_batch_in_thread, post_ids).result(timeout=300)

        for pid in post_ids:
            actions[pid] = "rendered" if pid in results else "render_failed"
        st.session_state["batch_actions"] = actions

        ok = len(results)
        failed = len(post_ids) - ok
        # Store summary in session_state — st.success/error before rerun gets wiped
        st.session_state["batch_render_msg"] = {"ok": ok, "failed": failed}
        st.rerun()
    except Exception as e:
        st.error(f"Batch render error: {e}")


def _approve_post(post_id: int, origin: str = "generate"):
    try:
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415

        config = _cached_config()
        db = _get_db()
        q = DraftQueue(config, db)
        ok = q.approve(post_id)
        db.close()

        if ok:
            if origin == "generate":
                st.session_state["last_post_action"] = "approved"
            st.rerun()
        else:
            st.error(f"Could not approve post #{post_id} (not in draft status?).")
    except Exception as e:
        st.error(f"Approve error: {e}")


def _reject_post(post_id: int, origin: str = "generate"):
    try:
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415

        config = _cached_config()
        db = _get_db()
        q = DraftQueue(config, db)
        ok = q.reject(post_id)
        db.close()

        if ok:
            if origin == "generate":
                st.session_state["last_post_action"] = "rejected"
            st.rerun()
        else:
            st.error(f"Could not reject post #{post_id} (not in draft status?).")
    except Exception as e:
        st.error(f"Reject error: {e}")


# ---------------------------------------------------------------------------
# Page 3 — Review Queue
# ---------------------------------------------------------------------------

def page_review():
    st.title("📋 Review Queue")

    try:
        from zcyber_xhs.models import PostStatus  # noqa: PLC0415

        db = _get_db()
        drafts = db.list_posts(status=PostStatus.DRAFT, limit=100)
        db.close()
    except Exception as e:
        st.error(f"Failed to load drafts: {e}")
        return

    if not drafts:
        st.info("No drafts — go to Generate tab to create posts.")
        return

    # ── Filter + select-all controls ──────────────────────────────────────
    all_archetypes = sorted({p.archetype for p in drafts})

    col_filter, col_sel = st.columns([3, 2])
    with col_filter:
        chosen_archetypes = st.multiselect(
            "Filter",
            options=all_archetypes,
            default=all_archetypes,
            label_visibility="collapsed",
            placeholder="Filter by archetype…",
        )
    with col_sel:
        sa, da = st.columns(2)
        with sa:
            if st.button("☑ All", key="rq_sel_all", use_container_width=True):
                for p in drafts:
                    if p.archetype in chosen_archetypes:
                        st.session_state[f"rq_cb_{p.id}"] = True
                st.rerun()
        with da:
            if st.button("☐ None", key="rq_sel_none", use_container_width=True):
                for p in drafts:
                    st.session_state[f"rq_cb_{p.id}"] = False
                st.rerun()

    filtered = [p for p in drafts if p.archetype in chosen_archetypes]
    if not filtered:
        st.info("No drafts match the selected archetypes.")
        return

    # Collect selected IDs from checkboxes (rendered below)
    # We pre-read session state so batch buttons know what's selected
    selected_ids = [
        p.id for p in filtered
        if st.session_state.get(f"rq_cb_{p.id}", False)
    ]

    # ── Batch action bar ──────────────────────────────────────────────────
    if selected_ids:
        st.caption(f"{len(selected_ids)} selected")
        ba1, ba2, ba3 = st.columns([1, 1, 4])
        with ba1:
            if st.button(
                f"✅ Approve {len(selected_ids)}",
                type="primary",
                use_container_width=True,
            ):
                for pid in selected_ids:
                    _queue_approve_silent(pid)
                    st.session_state.pop(f"rq_cb_{pid}", None)
                st.toast(f"Approved {len(selected_ids)} post(s)", icon="✅")
                st.rerun()
        with ba2:
            if st.button(f"❌ Reject {len(selected_ids)}", use_container_width=True):
                for pid in selected_ids:
                    _queue_reject_silent(pid)
                    st.session_state.pop(f"rq_cb_{pid}", None)
                st.toast(f"Rejected {len(selected_ids)} post(s)", icon="🗑️")
                st.rerun()
    else:
        st.caption(f"{len(filtered)} draft(s) — select posts to batch approve/reject")

    st.divider()

    # ── Two-column XHS-style grid ─────────────────────────────────────────
    arch_colors = {
        "problem_command": "#00C8FF",
        "everyday_panic":  "#FF7043",
        "mythbust":        "#FF5252",
        "before_after":    "#00E676",
        "tool_spotlight":  "#818CF8",
        "news_hook":       "#FFD54F",
        "ctf":             "#00E676",
    }

    pairs = [filtered[i:i+2] for i in range(0, len(filtered), 2)]

    for pair in pairs:
        cols = st.columns(2, gap="medium")
        for col, post in zip(cols, pair):
            with col:
                img_path = _resolve_image_path(post.image_path)
                img_exists = img_path and Path(img_path).exists()
                chip_color = arch_colors.get(post.archetype, "#888")

                with st.container(border=True):
                    # Select checkbox in top-right
                    # Initialize state before rendering — never pass value= alongside key=
                    if f"rq_cb_{post.id}" not in st.session_state:
                        st.session_state[f"rq_cb_{post.id}"] = False
                    st.checkbox(
                        "Select",
                        key=f"rq_cb_{post.id}",
                        label_visibility="collapsed",
                    )

                    # Thumbnail
                    if img_exists:
                        st.image(img_path, width="stretch")
                    else:
                        st.markdown(
                            "<div style='background:#1a1a2e;height:140px;border-radius:8px;"
                            "display:flex;align-items:center;justify-content:center;"
                            "color:#555;font-size:12px;'>⚠️ No image</div>",
                            unsafe_allow_html=True,
                        )

                    # Archetype chip + title
                    st.markdown(
                        f"<span style='background:{chip_color}22;color:{chip_color};"
                        f"border:1px solid {chip_color}55;border-radius:20px;"
                        f"padding:2px 10px;font-size:11px;font-weight:700;"
                        f"text-transform:uppercase;letter-spacing:1px'>"
                        f"{post.archetype}</span>",
                        unsafe_allow_html=True,
                    )
                    title_snippet = (post.title or "(no title)")[:36]
                    if len(post.title or "") > 36:
                        title_snippet += "…"
                    st.markdown(f"**{title_snippet}**")

                    # Body snippet (first 80 chars)
                    body_snippet = (post.body or "")[:80].replace("\n", " ")
                    if len(post.body or "") > 80:
                        body_snippet += "…"
                    st.caption(body_snippet)
                    st.caption(f"#{post.id}")

        # Expandable detail panels for this row
        for post in pair:
            img_path = _resolve_image_path(post.image_path)
            img_exists = img_path and Path(img_path).exists()

            with st.expander(f"#{post.id} · {post.archetype} · {post.title or '(no title)'}"):
                detail_left, detail_right = st.columns([3, 2])
                with detail_left:
                    st.text_area(
                        "Body", value=post.body or "", height=220,
                        disabled=True, key=f"rq_body_{post.id}",
                    )
                    tags_str = "  ".join(
                        t if t.startswith("#") else f"#{t}" for t in (post.tags or [])
                    )
                    st.caption(f"Tags: {tags_str or '(none)'}")
                with detail_right:
                    if img_exists:
                        st.image(img_path, width="stretch")
                    else:
                        st.caption("No image yet")

                btn_a, btn_r, btn_regen, btn_img, btn_del = st.columns([1, 1, 1.2, 1.2, 0.6])
                with btn_a:
                    if st.button("✅ Approve", key=f"approve_{post.id}"):
                        _queue_approve(post.id)
                with btn_r:
                    if st.button("❌ Reject", key=f"reject_{post.id}"):
                        _queue_reject(post.id)
                with btn_regen:
                    if st.button("🔄 Regen", key=f"regen_{post.id}"):
                        _regenerate_post(post.id, post.archetype)
                with btn_img:
                    if post.image_path:
                        if st.button("🖼️ Re-render", key=f"img_{post.id}",
                                     help="Re-render with latest template"):
                            ok = _render_image(post.id, force=True)
                            if ok:
                                st.toast(f"Re-rendered #{post.id}", icon="🖼️")
                            st.rerun()
                    else:
                        if st.button("🖼️ Render", key=f"img_{post.id}"):
                            _render_image(post.id)
                            st.rerun()
                with btn_del:
                    if st.button("🗑️", key=f"del_draft_{post.id}",
                                 help="Delete permanently"):
                        _delete_post(post.id)

        st.divider()


def _queue_approve_silent(post_id: int) -> bool:
    """Approve without showing UI feedback — used by batch actions."""
    try:
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415
        config = _cached_config()
        db = _get_db()
        ok = DraftQueue(config, db).approve(post_id)
        db.close()
        return ok
    except Exception:
        return False


def _queue_reject_silent(post_id: int) -> bool:
    """Reject without showing UI feedback — used by batch actions."""
    try:
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415
        config = _cached_config()
        db = _get_db()
        ok = DraftQueue(config, db).reject(post_id)
        db.close()
        return ok
    except Exception:
        return False


def _queue_approve(post_id: int):
    try:
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415

        config = _cached_config()
        db = _get_db()
        q = DraftQueue(config, db)
        ok = q.approve(post_id)
        db.close()

        if ok:
            st.toast(f"✅ Post #{post_id} approved.", icon="✅")
        else:
            st.error(f"Could not approve post #{post_id}.")
        st.rerun()
    except Exception as e:
        st.error(f"Approve error: {e}")


def _queue_reject(post_id: int):
    try:
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415

        config = _cached_config()
        db = _get_db()
        q = DraftQueue(config, db)
        ok = q.reject(post_id)
        db.close()

        if ok:
            st.toast(f"Post #{post_id} rejected.", icon="🗑️")
        else:
            st.error(f"Could not reject post #{post_id}.")
        st.rerun()
    except Exception as e:
        st.error(f"Reject error: {e}")


def _regenerate_post(old_post_id: int, archetype: str):
    try:
        from zcyber_xhs.orchestrator import Orchestrator  # noqa: PLC0415
        from zcyber_xhs.queue import DraftQueue  # noqa: PLC0415

        config = _cached_config()

        def _regen_in_thread(arch):
            db = _get_db()
            try:
                return Orchestrator(config, db).run(arch)
            finally:
                db.close()

        with st.spinner(f"Regenerating {archetype} post..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                new_post_id = pool.submit(_regen_in_thread, archetype).result(timeout=120)

        if new_post_id:
            db = _get_db()
            try:
                DraftQueue(config, db).reject(old_post_id)
            finally:
                db.close()
            st.toast(f"New post #{new_post_id} ready. Old #{old_post_id} rejected.", icon="🔄")
        else:
            st.error("Regeneration failed.")

        st.rerun()
    except Exception as e:
        st.error(f"Regenerate error: {e}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _delete_post(post_id: int) -> None:
    try:
        db = _get_db()
        ok = db.delete_post(post_id)
        db.close()
        if ok:
            st.success(f"Post #{post_id} deleted.")
        else:
            st.error(f"Post #{post_id} not found.")
        st.rerun()
    except Exception as e:
        st.error(f"Delete error: {e}")


# ---------------------------------------------------------------------------
# Page 4 — Approved
# ---------------------------------------------------------------------------

def page_approved():
    st.title("✅ Approved")
    st.caption("Two-column XHS-style preview. Click any card to expand full details and actions.")

    try:
        from zcyber_xhs.models import PostStatus  # noqa: PLC0415

        db = _get_db()
        posts = db.list_posts(status=PostStatus.APPROVED, limit=100)
        db.close()
    except Exception as e:
        st.error(f"Failed to load approved posts: {e}")
        return

    if not posts:
        st.info("No approved posts. Go to Review Queue to approve drafts.")
        return

    # ── Filter + select-all controls ──────────────────────────────────────
    all_archetypes = sorted({p.archetype for p in posts})

    col_filter, col_sel = st.columns([3, 2])
    with col_filter:
        chosen_archetypes = st.multiselect(
            "Filter",
            options=all_archetypes,
            default=all_archetypes,
            label_visibility="collapsed",
            placeholder="Filter by archetype…",
            key="appr_filter",
        )
    with col_sel:
        sa, da = st.columns(2)
        with sa:
            if st.button("☑ All", key="appr_sel_all", use_container_width=True):
                for p in posts:
                    if p.archetype in chosen_archetypes:
                        st.session_state[f"appr_cb_{p.id}"] = True
                st.rerun()
        with da:
            if st.button("☐ None", key="appr_sel_none", use_container_width=True):
                for p in posts:
                    st.session_state[f"appr_cb_{p.id}"] = False
                st.rerun()

    filtered_posts = [p for p in posts if p.archetype in chosen_archetypes]
    if not filtered_posts:
        st.info("No posts match the selected archetypes.")
        return

    selected_appr_ids = [
        p.id for p in filtered_posts
        if st.session_state.get(f"appr_cb_{p.id}", False)
    ]

    # ── Batch action bar ──────────────────────────────────────────────────
    if selected_appr_ids:
        st.caption(f"{len(selected_appr_ids)} selected")
        ba1, ba2, ba3, _ = st.columns([1.5, 1.5, 1.5, 3])
        with ba1:
            if st.button(f"↩️ To Draft ({len(selected_appr_ids)})", use_container_width=True):
                db = _get_db()
                from zcyber_xhs.models import PostStatus  # noqa: PLC0415
                for pid in selected_appr_ids:
                    db.update_post_status(pid, PostStatus.DRAFT)
                    st.session_state.pop(f"appr_cb_{pid}", None)
                db.close()
                st.toast(f"Moved {len(selected_appr_ids)} post(s) back to draft.", icon="↩️")
                st.rerun()
        with ba2:
            if st.button(f"🗑️ Delete ({len(selected_appr_ids)})", use_container_width=True):
                db = _get_db()
                for pid in selected_appr_ids:
                    db.delete_post(pid)
                    st.session_state.pop(f"appr_cb_{pid}", None)
                db.close()
                st.toast(f"Deleted {len(selected_appr_ids)} post(s).", icon="🗑️")
                st.rerun()
        with ba3:
            if st.button(f"🖼️ Re-render ({len(selected_appr_ids)})", use_container_width=True):
                _batch_rerender(selected_appr_ids)
    else:
        st.caption(f"{len(filtered_posts)} approved post(s) — select to batch action")

    st.divider()

    # ── Two-column XHS-style grid ─────────────────────────────────────────
    pairs = [filtered_posts[i:i+2] for i in range(0, len(filtered_posts), 2)]

    arch_colors = {
        "problem_command": "#00C8FF",
        "everyday_panic":  "#FF7043",
        "mythbust":        "#FF5252",
        "before_after":    "#00E676",
        "tool_spotlight":  "#818CF8",
        "news_hook":       "#FFD54F",
        "ctf":             "#00E676",
    }

    for pair in pairs:
        cols = st.columns(2, gap="medium")
        for col, post in zip(cols, pair):
            with col:
                img_path = _resolve_image_path(post.image_path)
                img_exists = img_path and Path(img_path).exists()
                chip_color = arch_colors.get(post.archetype, "#888")

                with st.container(border=True):
                    # Select checkbox
                    st.checkbox(
                        "Select", value=st.session_state.get(f"appr_cb_{post.id}", False),
                        key=f"appr_cb_{post.id}", label_visibility="collapsed",
                    )
                    # Thumbnail
                    if img_exists:
                        st.image(img_path, width="stretch")
                    else:
                        st.markdown(
                            "<div style='background:#1a1a2e;height:160px;border-radius:8px;"
                            "display:flex;align-items:center;justify-content:center;"
                            "color:#555;font-size:12px;'>⚠️ No image</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        f"<span style='background:{chip_color}22;color:{chip_color};"
                        f"border:1px solid {chip_color}55;border-radius:20px;"
                        f"padding:2px 10px;font-size:11px;font-weight:700;"
                        f"text-transform:uppercase;letter-spacing:1px'>"
                        f"{post.archetype}</span>",
                        unsafe_allow_html=True,
                    )
                    title_snippet = (post.title or "(no title)")[:36]
                    if len(post.title or "") > 36:
                        title_snippet += "…"
                    st.markdown(f"**{title_snippet}**")
                    st.caption(f"#{post.id}")

        # Expandable detail panels — one per post in this row
        for post in pair:
            img_path = _resolve_image_path(post.image_path)
            img_exists = img_path and Path(img_path).exists()

            with st.expander(f"#{post.id} · {post.archetype} · {post.title or '(no title)'}"):
                detail_left, detail_right = st.columns([3, 2])
                with detail_left:
                    st.text_area(
                        "Body", value=post.body or "", height=220,
                        disabled=True, key=f"appr_body_{post.id}",
                    )
                    tags_str = "  ".join(
                        t if t.startswith("#") else f"#{t}" for t in (post.tags or [])
                    )
                    st.caption(f"Tags: {tags_str or '(none)'}")
                with detail_right:
                    if img_exists:
                        st.image(img_path, width="stretch")
                    else:
                        st.caption("No image")

                btn_img_a, btn_back, btn_del, _ = st.columns([1.5, 1.5, 1, 3])
                with btn_img_a:
                    if post.image_path:
                        if st.button("🖼️ Re-render", key=f"appr_img_{post.id}",
                                     help="Re-render with latest template"):
                            ok = _render_image(post.id, force=True)
                            if ok:
                                st.toast(f"Re-rendered #{post.id}", icon="🖼️")
                            st.rerun()
                    else:
                        if st.button("🖼️ Render", key=f"appr_img_{post.id}"):
                            ok = _render_image(post.id)
                            if ok:
                                st.toast(f"Rendered #{post.id}", icon="🖼️")
                            st.rerun()
                with btn_back:
                    if st.button("↩️ To Draft", key=f"unapprove_{post.id}"):
                        try:
                            db = _get_db()
                            from zcyber_xhs.models import PostStatus  # noqa: PLC0415
                            db.update_post_status(post.id, PostStatus.DRAFT)
                            db.close()
                            st.toast(f"#{post.id} moved back to draft.", icon="↩️")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                with btn_del:
                    if st.button("🗑️ Delete", key=f"del_appr_{post.id}"):
                        _delete_post(post.id)

        st.divider()


# ---------------------------------------------------------------------------
# Page 5 — Export
# ---------------------------------------------------------------------------

def page_export():
    st.title("📤 Export")

    try:
        from zcyber_xhs.models import PostStatus  # noqa: PLC0415

        db = _get_db()
        approved = db.list_posts(status=PostStatus.APPROVED, limit=100)
        db.close()
    except Exception as e:
        st.error(f"Failed to load approved posts: {e}")
        return

    if not approved:
        st.info("No approved posts — approve some drafts first.")
        return

    # ── Filter + select-all controls ──────────────────────────────────────
    all_archetypes = sorted({p.archetype for p in approved})

    col_filter, col_sel = st.columns([3, 2])
    with col_filter:
        chosen_archetypes = st.multiselect(
            "Filter by archetype",
            options=all_archetypes,
            default=all_archetypes,
            label_visibility="collapsed",
            placeholder="Filter by archetype…",
        )
    with col_sel:
        sa, da = st.columns(2)
        with sa:
            if st.button("☑ All", use_container_width=True):
                for p in approved:
                    if p.archetype in chosen_archetypes:
                        st.session_state[f"export_cb_{p.id}"] = True
                st.rerun()
        with da:
            if st.button("☐ None", use_container_width=True):
                for p in approved:
                    st.session_state[f"export_cb_{p.id}"] = False
                st.rerun()

    filtered = [p for p in approved if p.archetype in chosen_archetypes]

    if not filtered:
        st.info("No posts match the selected archetypes.")
        return

    st.caption(f"Showing {len(filtered)} of {len(approved)} approved post(s)")

    # ── Per-post checkboxes ────────────────────────────────────────────────
    selected_ids: list[int] = []
    for post in filtered:
        img_tag = " 🖼️" if post.image_path else " ⚠️ no image"
        label = f"#{post.id} · **{post.archetype}** · {post.title or '(no title)'}{img_tag}"
        if f"export_cb_{post.id}" not in st.session_state:
            st.session_state[f"export_cb_{post.id}"] = True
        if st.checkbox(label, key=f"export_cb_{post.id}"):
            selected_ids.append(post.id)

    st.divider()

    # ── Options row ────────────────────────────────────────────────────────
    opt_col, _ = st.columns([2, 3])
    with opt_col:
        delete_after = st.checkbox(
            "🗑️ Delete posts after export",
            value=False,
            help="Removes exported posts from the queue once the folder is created. "
                 "Images stay on disk.",
        )

    # ── Missing-image warning ──────────────────────────────────────────────
    post_map = {p.id: p for p in filtered}
    missing_image_ids = [pid for pid in selected_ids if not post_map[pid].image_path]
    if missing_image_ids:
        st.warning(
            f"⚠️ {len(missing_image_ids)} selected post(s) have no image. "
            "Render them first or they'll export as text only."
        )
        if st.button(
            f"🖼️ Render {len(missing_image_ids)} Missing Image(s) — then export",
            type="secondary",
        ):
            _render_missing_then_export(missing_image_ids, selected_ids, delete_after)
            return

    # ── Export button ──────────────────────────────────────────────────────
    btn_label = f"📦 Export {len(selected_ids)} Post(s)" if selected_ids else "📦 Export Selected"
    if st.button(btn_label, type="primary", disabled=not selected_ids):
        _run_export(selected_ids, delete_after=delete_after)

    st.info("💡 Tip: Send the folder via WeChat 文件传输助手 to your phone.")


def _render_missing_then_export(
    missing_ids: list[int], all_selected_ids: list[int], delete_after: bool = False
) -> None:
    """Render images for posts missing them, then immediately run export."""
    try:
        from zcyber_xhs.orchestrator import Orchestrator  # noqa: PLC0415

        config = _cached_config()

        def _batch_in_thread(ids):
            db = _get_db()
            try:
                return Orchestrator(config, db).render_images_for_posts(ids)
            finally:
                db.close()

        with st.spinner(f"Rendering {len(missing_ids)} image(s) — one browser session..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(_batch_in_thread, missing_ids).result(timeout=300)

        ok = len(results)
        failed = len(missing_ids) - ok
        if ok:
            st.toast(f"🖼️ Rendered {ok} image(s). Exporting now...", icon="🖼️")
        if failed:
            st.warning(f"{failed} image(s) failed to render — exporting without them.")

    except Exception as e:
        st.error(f"Render error: {e} — exporting anyway.")

    _run_export(all_selected_ids, delete_after=delete_after)


def _run_export(post_ids: list[int], delete_after: bool = False):
    """Export selected posts to dated folders, optionally deleting them afterwards."""
    try:
        config = _cached_config()
        db = _get_db()

        export_root = config.base_dir / "output" / "manual_publish"
        export_root.mkdir(parents=True, exist_ok=True)

        exported_folders: list[Path] = []
        exported_post_ids: list[int] = []

        for post_id in post_ids:
            post = db.get_post(post_id)
            if not post:
                st.warning(f"Post #{post_id} not found, skipping.")
                continue

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
                    new_name = (
                        f"image_{idx:02d}{src_path.suffix}"
                        if len(paths) > 1
                        else f"image{src_path.suffix}"
                    )
                    shutil.copy2(src_path, dest / new_name)
                    image_count += 1

            # Write copy-paste friendly text file
            tags_formatted = " ".join(
                t if t.startswith("#") else f"#{t}" for t in (post.tags or [])
            )
            text_lines = [
                "=" * 60,
                f"POST #{post.id} — {post.archetype}",
                "=" * 60,
                "",
                "TITLE (copy into XHS title field, max 20 chars):",
                "-" * 60,
                post.title or "",
                "",
                "BODY (copy into XHS content area):",
                "-" * 60,
                post.body or "",
                "",
                "TAGS (type one by one in XHS):",
                "-" * 60,
                tags_formatted,
                "",
                "=" * 60,
                f"IMAGES: {image_count} file(s) in this folder",
                "=" * 60,
            ]
            (dest / "post.txt").write_text("\n".join(text_lines), encoding="utf-8")

            exported_folders.append(dest)
            exported_post_ids.append(post_id)

        # Delete exported posts if requested
        if delete_after and exported_post_ids:
            deleted = 0
            for pid in exported_post_ids:
                if db.delete_post(pid):
                    deleted += 1
                    # Clear the export checkbox so it doesn't linger
                    st.session_state.pop(f"export_cb_{pid}", None)
            st.toast(f"🗑️ Deleted {deleted} exported post(s) from queue.", icon="🗑️")

        db.close()

        if exported_folders:
            st.session_state["last_export_root"] = str(export_root)
            st.session_state["last_export_folders"] = [str(f) for f in exported_folders]
        else:
            st.warning("No posts were exported.")

    except Exception as e:
        st.error(f"Export error: {e}")

    # Show export results persistently (survives reruns)
    if st.session_state.get("last_export_folders"):
        folders = st.session_state["last_export_folders"]
        export_root_str = st.session_state.get("last_export_root", "")
        st.success(f"✅ Exported {len(folders)} post(s) — ready to send via WeChat.")
        for f in folders:
            st.code(f)
        col_open, col_clear = st.columns([2, 1])
        with col_open:
            if st.button("📂 Open Folder in Explorer"):
                os.startfile(export_root_str)
        with col_clear:
            if st.button("✕ Clear"):
                st.session_state.pop("last_export_folders", None)
                st.session_state.pop("last_export_root", None)
                st.rerun()


# ---------------------------------------------------------------------------
# Sidebar navigation and main router
# ---------------------------------------------------------------------------

def main():
    st.sidebar.title("🔐 ZCyber XHS")
    st.sidebar.caption("Local content pipeline tool")
    if st.sidebar.button("🔄 Reload Config", help="Reload config.yaml if you changed settings"):
        st.cache_resource.clear()
        st.rerun()
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        options=["📊 Dashboard", "⚡ Generate", "📋 Review Queue", "✅ Approved", "📤 Export"],
        label_visibility="collapsed",
    )

    if page == "📊 Dashboard":
        page_dashboard()
    elif page == "⚡ Generate":
        page_generate()
    elif page == "📋 Review Queue":
        page_review()
    elif page == "✅ Approved":
        page_approved()
    elif page == "📤 Export":
        page_export()


if __name__ == "__main__":
    main()
