# zcyber-xhs-pipeline

Automated cybersecurity content pipeline for Xiaohongshu. Generates bite-sized cyber tips for non-professionals, renders visual text cards, and publishes on a schedule — funneling traffic to **zcybernews**.

## Quick Start

```bash
# 1. Clone and install
git clone <your-repo-url>
cd zcyber-xhs
pip install -e ".[dev]"
playwright install chromium

# 2. Configure
cp .env.example .env
# Edit .env with your DeepSeek API key

# 3. Generate your first post
zcyber generate -a problem_command

# 4. Review and approve
zcyber queue list
zcyber queue show 1
zcyber queue approve 1

# 5. Start the scheduler (runs daily)
zcyber run
```

## Content Archetypes

| Day | Archetype | Description |
|-----|-----------|-------------|
| Mon | `problem_command` | Problem + one command solution |
| Tue | `tool_spotlight` | One tool, five uses |
| Wed | `everyday_panic` | Relatable panic moments |
| Thu | `before_after` | Wrong way vs right way |
| Fri | `news_hook` | CVE/breach news tie-in |
| Sat | `mythbust` | Security myth debunking |
| Sun | `ctf` | Mini CTF challenge |

## CLI Commands

```bash
zcyber generate -a <archetype> [-t <topic>]  # Generate a post
zcyber queue list [-s <status>]               # List queue
zcyber queue show <id>                        # Show post details
zcyber queue approve <id>                     # Approve for publishing
zcyber queue reject <id>                      # Reject a draft
zcyber publish [<id>]                         # Publish next approved
zcyber status                                 # Pipeline status
zcyber run                                    # Start scheduler
```

## Architecture

```
Cron/APScheduler
  -> Topic Discovery (YAML banks + dedup)
  -> LLM Generation (DeepSeek/Kimi, structured JSON)
  -> Image Rendering (Playwright HTML->PNG)
  -> Draft Queue (SQLite, human review)
  -> Publisher (xiaohongshu-mcp)
```

## Setup xiaohongshu-mcp

```bash
bash scripts/bootstrap_mcp.sh
```

## Docker

```bash
docker compose up -d          # Start scheduler
docker compose run pipeline generate -a problem_command  # One-off
```

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/
pytest -v
```
