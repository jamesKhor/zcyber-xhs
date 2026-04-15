# zcyber-xhs — Project Guide for Claude

This file gives Claude full context to work on this project from any session. It pairs with the global agent org in `~/.claude/agents/`.

---

## What this project is

A **Python pipeline** that generates bite-sized cybersecurity content cards for **Xiaohongshu** (小红书) and publishes them on a schedule. Its sole purpose is to **funnel discovery-stage users to the main site, `zcybernews`**.

Think of it as the **top of the marketing funnel** while `zcybernews` is the **destination**:

```
XHS users (non-professionals, curious about cyber)
  → see daily 1080×1440 visual card (zcyber-xhs)
  → follow account, tap link-in-bio
  → land on zcybernews (zh locale)
  → read full article
  → (future) subscribe / convert
```

**This is the companion to `../zcybernews`**. They are ONE marketing system. Maya owns both.

---

## Tech stack

| Layer | Tech |
|-------|------|
| Language | Python 3.11+ |
| Package manager | `pip install -e ".[dev]"` (hatchling build backend) |
| CLI | `click` — entry point `zcyber` (see `[project.scripts]`) |
| LLM | DeepSeek or Kimi via OpenAI-compatible SDK (`openai` + `httpx`) |
| Image rendering | Jinja2 HTML templates → Playwright Chromium → PNG |
| Database | SQLite + SQLAlchemy (local file `zcyber_xhs.db`) |
| Scheduler | APScheduler (daily generate + publish) |
| Publisher | [xiaohongshu-mcp](https://github.com/...) (MCP server at `http://localhost:18060`) |
| Review flow | Telegram bot (`python-telegram-bot`) for human approval |
| Deploy | Docker Compose (`docker compose up -d`) |
| Test/lint | `pytest` + `ruff` |

---

## Directory structure

```
zcyber-xhs/
├── src/zcyber_xhs/
│   ├── cli.py            # click CLI entry
│   ├── config.py         # YAML config loading + env
│   ├── db.py             # SQLAlchemy session + schema
│   ├── models.py         # Pydantic + SQLA models
│   ├── discover/         # Topic sourcing (YAML banks + dedup)
│   ├── generate/         # LLM prompt → structured JSON
│   ├── images/           # Jinja2 + Playwright HTML→PNG
│   ├── queue.py          # Draft queue management
│   ├── review_bot.py     # Telegram review workflow
│   ├── publish.py        # xiaohongshu-mcp caller
│   ├── scheduler.py      # APScheduler wiring
│   ├── orchestrator.py   # Top-level pipeline runner
│   ├── safety.py         # Content moderation
│   └── analytics.py      # Post-publish metrics
├── config/
│   ├── config.yaml       # LLM, schedule, publishing, content CTA
│   ├── prompts/          # Jinja2 prompt templates per archetype
│   ├── topic_banks/      # YAML topic pools per archetype
│   └── backgrounds/      # Image background assets
├── scripts/
│   └── bootstrap_mcp.sh  # Set up xiaohongshu-mcp locally
├── tests/                # pytest — analytics, db, generate, safety
├── output/images/        # Generated PNG cards
├── zcyber_xhs.db         # SQLite draft queue (gitignored)
├── Dockerfile            # Python + Playwright chromium
├── docker-compose.yml    # Scheduler container
└── pyproject.toml        # hatchling build, ruff, pytest config
```

---

## Content archetypes (the 7-day rotation)

Each day of the week has one archetype. Generator picks topic from the matching YAML bank in `config/topic_banks/`.

| Day | Archetype | What it is |
|-----|-----------|------------|
| Mon | `problem_command` | Problem statement + one-line command fix |
| Tue | `tool_spotlight` | One tool, five uses |
| Wed | `everyday_panic` | Relatable security panic moment |
| Thu | `before_after` | Wrong way vs right way |
| Fri | `news_hook` | **Tie into recent CVE/breach** — prime funnel to zcybernews article |
| Sat | `mythbust` | Common security myth debunked |
| Sun | `ctf` | Mini CTF challenge |

### Why the rotation matters for Maya

- Variety prevents feed fatigue
- Friday `news_hook` is the **most important** for driving traffic to zcybernews (deep cross-project tie)
- When zcybernews publishes a big story, the Friday hook should reference it

---

## Daily schedule (config/config.yaml)

- **08:00** — generator runs, creates draft for today's archetype
- **Anytime** — operator reviews via Telegram bot, approves or rejects
- **12:00** — publisher drains approved queue
- **Limits:** max 2 posts/day · min 4h between · ±20min jitter · 3 retries

---

## Workflow CLI (the `zcyber` command)

```bash
zcyber generate -a problem_command        # generate for a specific archetype
zcyber generate -a news_hook -t "cve-2026-12345"  # with topic override
zcyber queue list [-s approved|pending|published]
zcyber queue show <id>
zcyber queue approve <id>
zcyber queue reject <id>
zcyber publish [<id>]                      # publish specific or next approved
zcyber status                              # pipeline health
zcyber run                                 # start scheduler (production)
```

---

## Funnel contract with zcybernews

**zcybernews publishes articles. zcyber-xhs drives traffic to them. They are one system.**

### Current funnel signal (implicit)

Every XHS card ends with the config CTA:
```yaml
content:
  cta: "更多威胁情报 → 主页 zcybernews"
```

Tag: `#zcybernews` is on every post.

### Future: explicit cross-project signaling

When zcybernews pipeline publishes a high-severity article:
1. **zcybernews** emits a `news_published` event (to a shared queue / webhook / file)
2. **zcyber-xhs** reads it and uses it as the topic for Friday's `news_hook` archetype
3. Card renders with the article slug as the CTA target (not just homepage)
4. Maya measures conversion: XHS click → zcybernews article view

**Not yet built.** Proposed as a Maya-led Raymond+Raymond-of-xhs initiative.

---

## Operator conventions

- **Always use `uv` or `pip install -e .` from repo root** — never edit site-packages
- **Never commit `.env`** — contains DeepSeek API key
- **Never commit `zcyber_xhs.db`** — local draft state
- **Every image output** is a 1080×1440 PNG from a Jinja template — check `output/images/` before publishing
- **XHS publishing goes through xiaohongshu-mcp** — never call XHS APIs directly
- **Review bot is the safety gate** — no auto-publish without human approve

---

## Global agents available here (from ~/.claude/agents/)

Because this is a Python + LLM + image-rendering project, these agents are the most useful:

| Agent | When to call |
|-------|--------------|
| **Maya — Marketing Lead** | Primary owner. Strategy, monetization, campaign design, cross-project funnel |
| **Xiaohongshu Specialist** | Tactical XHS content + trends — Maya delegates |
| **Prompt Engineer** | Generation prompts in `config/prompts/` — safety guards, hallucination prevention |
| **Raymond — Engineering Lead** | Code changes to `src/zcyber_xhs/` — triages to specialists |
| **AI Engineer** | DeepSeek/Kimi integration, prompt → JSON pipeline |
| **Debugger** | When a published card looks wrong or pipeline fails |
| **Test Automator** | pytest coverage for generate/safety/db |
| **Code Reviewer** | All PRs before merge |
| **Harness Engineer** | `.claude/` config, MCP server wiring (xiaohongshu-mcp) |
| **Sam — Chief of Staff** | Performance reviews of agents working on this project |

Full roster: `~/.claude/agents/ORG_CHART.md`

---

## Cross-project pairings (zcybernews ↔ zcyber-xhs)

| When you're in `zcybernews` | Matching moment in `zcyber-xhs` |
|------------------------------|----------------------------------|
| Pipeline publishes a critical-severity article | Flag it as Friday `news_hook` topic |
| Admin publishes a big story | Generate same-day XHS card |
| Content team rewrites an article | Update XHS card if still in queue |
| Analytics shows a post driving traffic | Amplify with more XHS cards on same topic |
| Maya specs a campaign | Specs both EN (zcybernews) and ZH (XHS) deliverables |

---

## How to continue in a new session

Tell Claude: *"Read CLAUDE.md and continue"* — full context reload.

Or invoke any agent directly. Examples:
- *"Maya, what's our funnel conversion from XHS to zcybernews?"*
- *"Maya, plan this Friday's news_hook card"*
- *"Prompt Engineer, audit the generate/ prompts for hallucination"*
- *"Raymond, add a retry backoff to publish.py"*
- *"Debugger, why did yesterday's post fail to render?"*

---

## See also

- **`../zcybernews/CLAUDE.md`** — the destination site
- **`~/.claude/agents/ORG_CHART.md`** — full agent roster
- **`~/.claude/projects/.../memory/MEMORY.md`** — cross-session memory (script vs agent principle lives here)
