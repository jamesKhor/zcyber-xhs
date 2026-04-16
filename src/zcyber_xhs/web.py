"""FastAPI web application — replaces the Streamlit GUI."""

from __future__ import annotations

import concurrent.futures
import io
import json
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------

app = FastAPI(title="ZCyber Content Pipeline")

# Resolve project root and template/static paths
_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent  # src/zcyber_xhs → src → project root
_TEMPLATES_DIR = _HERE / "web_templates"
_OUTPUT_DIR = _PROJECT_ROOT / "output" / "images"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
app.mount("/static/images", StaticFiles(directory=str(_OUTPUT_DIR)), name="images")

# ---------------------------------------------------------------------------
# Global singletons (lazy-loaded)
# ---------------------------------------------------------------------------

_config = None
_config_lock = threading.Lock()


def get_config():
    global _config
    if _config is None:
        with _config_lock:
            if _config is None:
                import sys
                sys.path.insert(0, str(_HERE.parent.parent / "src"))
                from zcyber_xhs.config import Config
                _config = Config()
    return _config


def get_db():
    """Return a fresh DB connection (each request/thread gets its own)."""
    from zcyber_xhs.db import Database
    config = get_config()
    db = Database(config.base_dir / "zcyber_xhs.db")
    db.init()
    return db


# ---------------------------------------------------------------------------
# In-memory job store (single-user, ephemeral across restarts is fine)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

_active_profile_slug = "cybersec"
_active_profile_lock = threading.Lock()


def _get_profiles() -> list[dict]:
    """Load all profile YAML files from config/profiles/."""
    try:
        profiles_dir = get_config().base_dir / "config" / "profiles"
        profiles = []
        for f in sorted(profiles_dir.glob("*.yaml")):
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                if data:
                    profiles.append(data)
        return profiles
    except Exception:
        return [{"name": "Cybersecurity", "slug": "cybersec", "icon": "🔐", "status": None}]


def _get_active_profile() -> dict:
    """Return the active profile dict."""
    for p in _get_profiles():
        if p.get("slug") == _active_profile_slug:
            return p
    return {"name": "Cybersecurity", "slug": "cybersec", "icon": "🔐"}


def _new_job() -> str:
    job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "post_ids": [], "errors": [], "done": 0, "total": 0}
    return job_id

def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)

def _get_job(job_id: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(job_id, {"status": "not_found"}))

# ---------------------------------------------------------------------------
# Archetype metadata
# ---------------------------------------------------------------------------

ARCHETYPES = [
    ("problem_command", "命令技巧",  "Command Tip"),
    ("real_story",      "真实事件",  "Real Story"),
    ("everyday_panic",  "日常惊魂",  "Everyday Panic"),
    ("rank_war",        "观点对决",  "Rank War"),
    ("mythbust",        "辟谣",      "Myth Bust"),
    ("news_hook",       "时事钩子",  "News Hook"),
    ("ctf",             "CTF挑战",  "CTF Challenge"),
]

BANK_ARCHETYPES = {
    "problem_command", "real_story", "everyday_panic",
    "rank_war", "mythbust", "tool_spotlight", "before_after",
}

ARCHETYPE_LABEL = {a: f"{zh} / {en}" for a, zh, en in ARCHETYPES}
ARCHETYPE_ZH = {a: zh for a, zh, _ in ARCHETYPES}

# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

def _resolve_image(image_path: str | None) -> str | None:
    """Return URL path for the FIRST image, or None."""
    if not image_path:
        return None
    if image_path.startswith("["):
        try:
            paths = json.loads(image_path)
            if paths:
                image_path = str(paths[0])
            else:
                return None
        except Exception:
            return None
    p = Path(image_path)
    if p.exists():
        return f"/static/images/{p.name}"
    return None


def _resolve_all_images(image_path: str | None) -> list[str]:
    """Return URL paths for ALL images (carousel support)."""
    if not image_path:
        return []
    if image_path.startswith("["):
        try:
            paths = json.loads(image_path)
        except Exception:
            paths = []
    else:
        paths = [image_path]
    result = []
    for p_str in paths:
        p = Path(p_str)
        if p.exists():
            result.append(f"/static/images/{p.name}")
    return result


def _status_color(status: str) -> str:
    return {
        "draft":     "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
        "approved":  "text-green-400 bg-green-400/10 border-green-400/30",
        "published": "text-cyan-400 bg-cyan-400/10 border-cyan-400/30",
        "rejected":  "text-red-400 bg-red-400/10 border-red-400/30",
        "failed":    "text-gray-400 bg-gray-400/10 border-gray-400/30",
    }.get(status, "text-gray-400")


def _base_context(request: Request) -> dict:
    """Context shared by every page (sidebar counts)."""
    try:
        from zcyber_xhs.models import PostStatus
        db = get_db()
        try:
            counts = {
                "draft":     len(db.list_posts(status=PostStatus.DRAFT, limit=500)),
                "approved":  len(db.list_posts(status=PostStatus.APPROVED, limit=500)),
                "published": len(db.list_posts(status=PostStatus.PUBLISHED, limit=500)),
            }
        finally:
            db.close()
    except Exception:
        counts = {"draft": 0, "approved": 0, "published": 0}
    return {
        "request": request,
        "counts": counts,
        "active_profile": _get_active_profile(),
        "profiles": _get_profiles(),
    }

# ---------------------------------------------------------------------------
# Routes — pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/review")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = _base_context(request)
    try:
        from zcyber_xhs.discover.topic_bank import TopicBank
        db = get_db()
        try:
            bank = TopicBank(get_config().base_dir / "config", db)
            topics_remaining = sum(bank.count_remaining(a) for a in BANK_ARCHETYPES)
            recent_posts = db.list_posts(limit=15)
        finally:
            db.close()
    except Exception:
        topics_remaining = 0
        recent_posts = []
    ctx.update({
        "topics_remaining": topics_remaining,
        "recent_posts": recent_posts,
        "resolve_image": _resolve_image,
        "status_color": _status_color,
        "archetype_zh": ARCHETYPE_ZH,
    })
    return templates.TemplateResponse(ctx["request"], "dashboard.html", ctx)


@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request):
    ctx = _base_context(request)
    try:
        from zcyber_xhs.discover.topic_bank import TopicBank
        db = get_db()
        try:
            bank = TopicBank(get_config().base_dir / "config", db)
            remaining = {a: bank.count_remaining(a) for a in BANK_ARCHETYPES}
        finally:
            db.close()
    except Exception:
        remaining = {}
    ctx.update({"archetypes": ARCHETYPES, "remaining": remaining})
    return templates.TemplateResponse(ctx["request"], "generate.html", ctx)


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request, archetype: str = ""):
    ctx = _base_context(request)
    try:
        from zcyber_xhs.models import PostStatus
        db = get_db()
        try:
            posts = db.list_posts(status=PostStatus.DRAFT, limit=200)
        finally:
            db.close()
    except Exception:
        posts = []
    if archetype:
        posts = [p for p in posts if p.archetype == archetype]
    all_archetypes = sorted({p.archetype for p in posts})
    ctx.update({
        "posts": posts,
        "selected_archetype": archetype,
        "all_archetypes": all_archetypes,
        "resolve_image": _resolve_image,
        "status_color": _status_color,
        "archetype_zh": ARCHETYPE_ZH,
    })
    return templates.TemplateResponse(ctx["request"], "review.html", ctx)


@app.get("/approved", response_class=HTMLResponse)
async def approved_page(request: Request, archetype: str = ""):
    ctx = _base_context(request)
    try:
        from zcyber_xhs.models import PostStatus
        db = get_db()
        try:
            posts = db.list_posts(status=PostStatus.APPROVED, limit=200)
        finally:
            db.close()
    except Exception:
        posts = []
    if archetype:
        posts = [p for p in posts if p.archetype == archetype]
    all_archetypes = sorted({p.archetype for p in posts})
    ctx.update({
        "posts": posts,
        "selected_archetype": archetype,
        "all_archetypes": all_archetypes,
        "resolve_image": _resolve_image,
        "status_color": _status_color,
        "archetype_zh": ARCHETYPE_ZH,
    })
    return templates.TemplateResponse(ctx["request"], "approved.html", ctx)


@app.get("/export", response_class=HTMLResponse)
async def export_page(request: Request, archetype: str = ""):
    ctx = _base_context(request)
    try:
        from zcyber_xhs.models import PostStatus
        db = get_db()
        try:
            posts = db.list_posts(status=PostStatus.APPROVED, limit=200)
        finally:
            db.close()
    except Exception:
        posts = []
    if archetype:
        posts = [p for p in posts if p.archetype == archetype]
    all_archetypes = sorted({p.archetype for p in posts})
    ctx.update({
        "posts": posts,
        "selected_archetype": archetype,
        "all_archetypes": all_archetypes,
        "resolve_image": _resolve_image,
        "archetype_zh": ARCHETYPE_ZH,
    })
    return templates.TemplateResponse(ctx["request"], "export.html", ctx)

# ---------------------------------------------------------------------------
# Routes — API / HTMX actions
# ---------------------------------------------------------------------------

@app.post("/api/generate")
async def api_generate(
    background_tasks: BackgroundTasks,
    archetype: str = Form(...),
    count: int = Form(1),
    text_only: bool = Form(False),
    topic_override: str = Form(""),
    language: str = Form("zh"),
):
    """Start a generation job. Returns a job_id for polling."""
    job_id = _new_job()
    _update_job(job_id, total=count)

    def _run():
        try:
            from zcyber_xhs.discover.topic_bank import TopicBank
            from zcyber_xhs.orchestrator import Orchestrator

            config = get_config()
            override = topic_override.strip() or None

            # Pre-pick topics atomically (prevent race on parallel workers)
            if override:
                topics = [override] * count
            elif archetype in BANK_ARCHETYPES:
                db = get_db()
                try:
                    bank = TopicBank(config.base_dir / "config", db)
                    picked = bank.pick_n_topics(archetype, count)
                finally:
                    db.close()
                topics = [t.slug for t in picked]
                _update_job(job_id, total=len(topics))
            else:
                topics = [None] * count

            post_ids = []
            errors = []

            def _worker(topic):
                db = get_db()
                try:
                    return Orchestrator(config, db).run(
                        archetype, topic, text_only, language=language
                    )
                finally:
                    db.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 4)) as pool:
                futures = {pool.submit(_worker, t): i for i, t in enumerate(topics)}
                for future in concurrent.futures.as_completed(futures, timeout=180):
                    try:
                        pid = future.result()
                        if pid:
                            post_ids.append(pid)
                    except Exception as e:
                        errors.append(str(e))
                    _update_job(job_id, done=len(post_ids) + len(errors))

            _update_job(job_id, status="done", post_ids=post_ids, errors=errors)
        except Exception as e:
            _update_job(job_id, status="error", error=str(e))

    background_tasks.add_task(_run)
    # Return HTMX fragment that starts polling
    html = f"""
    <div id="gen-status"
         hx-get="/api/jobs/{job_id}"
         hx-trigger="every 1500ms"
         hx-target="#gen-status"
         hx-swap="outerHTML"
         class="flex items-center gap-3 text-brand-dim mt-4">
      <div class="w-5 h-5 border-2 border-brand-cyan border-t-transparent rounded-full animate-spin"></div>
      <span class="text-sm">Generating {count} post(s)…</span>
    </div>
    """
    return HTMLResponse(html)


@app.get("/api/jobs/{job_id}", response_class=HTMLResponse)
async def api_job_status(request: Request, job_id: str):
    """Poll endpoint — returns HTML fragment. HTMX replaces #gen-status."""
    job = _get_job(job_id)
    status = job.get("status")
    done = job.get("done", 0)
    total = job.get("total", 1)
    post_ids = job.get("post_ids", [])
    errors = job.get("errors", [])

    if status == "running":
        pct = int((done / max(total, 1)) * 100)
        return HTMLResponse(f"""
        <div id="gen-status"
             hx-get="/api/jobs/{job_id}"
             hx-trigger="every 1500ms"
             hx-target="#gen-status"
             hx-swap="outerHTML"
             class="mt-4 space-y-2">
          <div class="flex items-center gap-3 text-sm text-brand-dim">
            <div class="w-4 h-4 border-2 border-brand-cyan border-t-transparent rounded-full animate-spin"></div>
            <span>{done}/{total} complete…</span>
          </div>
          <div class="w-full bg-brand-border rounded-full h-1.5">
            <div class="bg-brand-cyan h-1.5 rounded-full transition-all" style="width:{pct}%"></div>
          </div>
        </div>""")

    if status == "error":
        return HTMLResponse(f"""
        <div id="gen-status" class="mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
          ✗ Generation failed: {job.get('error', 'Unknown error')}
        </div>""")

    # Done — fetch the posts and show result cards
    ctx = {"request": request, "post_ids": post_ids, "errors": errors,
           "resolve_image": _resolve_image, "status_color": _status_color,
           "archetype_zh": ARCHETYPE_ZH}
    if post_ids:
        db = get_db()
        try:
            ctx["posts"] = [p for p in [db.get_post(pid) for pid in post_ids] if p]
        finally:
            db.close()
    else:
        ctx["posts"] = []
    return templates.TemplateResponse(ctx["request"], "fragments/gen_results.html", ctx)


@app.post("/api/posts/{post_id}/approve", response_class=HTMLResponse)
async def api_approve(post_id: int):
    try:
        from zcyber_xhs.queue import DraftQueue
        config = get_config()
        db = get_db()
        try:
            DraftQueue(config, db).approve(post_id)
        finally:
            db.close()
        return HTMLResponse(_status_pill("approved"))
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400 text-xs">Error: {e}</span>')


@app.post("/api/posts/{post_id}/reject", response_class=HTMLResponse)
async def api_reject(post_id: int):
    try:
        from zcyber_xhs.queue import DraftQueue
        config = get_config()
        db = get_db()
        try:
            DraftQueue(config, db).reject(post_id)
        finally:
            db.close()
        return HTMLResponse(_status_pill("rejected"))
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400 text-xs">Error: {e}</span>')


@app.post("/api/posts/{post_id}/to-draft", response_class=HTMLResponse)
async def api_to_draft(post_id: int):
    try:
        db = get_db()
        try:
            db.update_post_status(post_id, "draft")
        finally:
            db.close()
        return HTMLResponse(_status_pill("draft"))
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400 text-xs">Error: {e}</span>')


@app.delete("/api/posts/{post_id}", response_class=HTMLResponse)
async def api_delete(post_id: int):
    try:
        db = get_db()
        try:
            db.delete_post(post_id)
        finally:
            db.close()
        return HTMLResponse("")  # Empty = HTMX removes the element
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400 text-xs">Error: {e}</span>')


@app.post("/api/posts/{post_id}/render", response_class=HTMLResponse)
async def api_render(background_tasks: BackgroundTasks, post_id: int, force: bool = False):
    """Start image render job. Returns polling fragment."""
    job_id = _new_job()
    _update_job(job_id, total=1)

    def _run():
        try:
            from zcyber_xhs.orchestrator import Orchestrator
            config = get_config()
            db = get_db()
            try:
                path = Orchestrator(config, db).render_image_for_post(post_id, force=force)
            finally:
                db.close()
            if path:
                _update_job(
                    job_id,
                    status="done",
                    image_url=f"/static/images/{Path(path).name}",
                    post_id=post_id,
                )
            else:
                _update_job(job_id, status="error", error="No image produced")
        except Exception as e:
            _update_job(job_id, status="error", error=str(e))

    background_tasks.add_task(_run)
    return HTMLResponse(f"""
    <div id="render-{post_id}"
         hx-get="/api/render-status/{job_id}?post_id={post_id}"
         hx-trigger="every 2000ms"
         hx-target="#render-{post_id}"
         hx-swap="outerHTML"
         class="flex items-center gap-2 text-xs text-brand-dim">
      <div class="w-3 h-3 border border-brand-cyan border-t-transparent rounded-full animate-spin"></div>
      Rendering…
    </div>""")


@app.get("/api/render-status/{job_id}", response_class=HTMLResponse)
async def api_render_status(job_id: str, post_id: int):
    job = _get_job(job_id)
    status = job.get("status")
    if status == "running":
        return HTMLResponse(f"""
        <div id="render-{post_id}"
             hx-get="/api/render-status/{job_id}?post_id={post_id}"
             hx-trigger="every 2000ms"
             hx-target="#render-{post_id}"
             hx-swap="outerHTML"
             class="flex items-center gap-2 text-xs text-brand-dim">
          <div class="w-3 h-3 border border-brand-cyan border-t-transparent rounded-full animate-spin"></div>
          Rendering…
        </div>""")
    if status == "done":
        img_url = job.get("image_url", "")
        return HTMLResponse(f"""
        <div id="render-{post_id}" class="space-y-2">
          <img src="{img_url}" class="w-full rounded-lg border border-brand-border" loading="lazy">
          <p class="text-xs text-green-400">✓ Image ready</p>
        </div>""")
    err = job.get("error", "Render failed")
    return HTMLResponse(
        f'<div id="render-{post_id}" class="text-xs text-red-400">✗ {err}</div>'
    )


@app.get("/api/posts/{post_id}/modal", response_class=HTMLResponse)
async def api_post_modal(request: Request, post_id: int):
    """Returns full post detail for modal."""
    db = get_db()
    try:
        post = db.get_post(post_id)
    finally:
        db.close()
    if not post:
        return HTMLResponse("<p class='text-red-400'>Post not found</p>")

    # Extract carousel_slides from stored payload for text preview
    carousel_slides = []
    if post.payload_json:
        try:
            payload = json.loads(post.payload_json)
            carousel_slides = payload.get("carousel_slides", [])
        except Exception:
            carousel_slides = []

    ctx = {
        "request": request, "post": post,
        "resolve_image": _resolve_image,
        "resolve_all_images": _resolve_all_images,
        "carousel_slides": carousel_slides,
        "status_color": _status_color,
        "archetype_zh": ARCHETYPE_ZH,
    }
    return templates.TemplateResponse(ctx["request"], "fragments/post_modal.html", ctx)


@app.post("/api/export")
async def api_export(post_ids: str = Form(""), delete_after: bool = Form(False)):
    """Download selected approved posts as ZIP (images + captions txt)."""
    ids = [int(x) for x in post_ids.split(",") if x.strip()]
    if not ids:
        return HTMLResponse('<p class="text-red-400">No posts selected.</p>', status_code=400)

    db = get_db()
    try:
        posts = [p for p in [db.get_post(pid) for pid in ids] if p]
    finally:
        db.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for post in posts:
            # Caption file
            caption = f"{post.title}\n\n{post.body}\n\n{' '.join(post.tags or [])}"
            zf.writestr(f"post_{post.id}_{post.archetype}_caption.txt", caption.encode("utf-8"))
            # Image(s)
            if post.image_path:
                if post.image_path.startswith("["):
                    try:
                        img_paths = json.loads(post.image_path)
                    except Exception:
                        img_paths = []
                else:
                    img_paths = [post.image_path]
                for i, img_path in enumerate(img_paths):
                    p = Path(img_path)
                    if p.exists():
                        suffix = f"_{i+1}" if len(img_paths) > 1 else ""
                        zf.write(p, f"post_{post.id}_{post.archetype}{suffix}.png")

    if delete_after:
        db2 = get_db()
        try:
            for pid in ids:
                db2.delete_post(pid)
        finally:
            db2.close()

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=zcyber_export_{ts}.zip"},
    )


@app.post("/api/profile/set", response_class=RedirectResponse)
async def set_profile(profile_slug: str = Form(...), redirect_to: str = Form("/")):
    global _active_profile_slug
    with _active_profile_lock:
        _active_profile_slug = profile_slug
    return RedirectResponse(url=redirect_to, status_code=303)


def _status_pill(status: str) -> str:
    colors = _status_color(status)
    labels = {"draft": "Draft", "approved": "Approved", "rejected": "Rejected",
              "published": "Published", "failed": "Failed"}
    label = labels.get(status, status)
    return (
        f'<span class="inline-flex items-center px-2.5 py-0.5 rounded-full'
        f' text-xs font-medium border {colors}">{label}</span>'
    )


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("zcyber_xhs.web:app", host="0.0.0.0", port=8080, reload=True)
