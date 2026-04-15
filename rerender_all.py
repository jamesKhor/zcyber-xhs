"""One-time script: re-render ALL posts that have an existing image.

Run once from the project root:
    python rerender_all.py

This forces every saved image to be rebuilt with the latest HTML templates
(bigger fonts, new design). Safe to run multiple times — just overwrites PNGs.
"""
import sys
import io
from pathlib import Path

# Fix Windows console encoding for Chinese/Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent / "src"))

from zcyber_xhs.config import Config
from zcyber_xhs.db import Database
from zcyber_xhs.orchestrator import Orchestrator

project_root = Path(__file__).parent
config = Config(config_path=project_root / "config" / "config.yaml")
db = Database(project_root / "zcyber_xhs.db")
db.init()

posts = db.list_posts(limit=200)
to_rerender = [p for p in posts if p.image_path]

print(f"Found {len(to_rerender)} post(s) with images to re-render.\n")

orch = Orchestrator(config, db)

for i, post in enumerate(to_rerender, 1):
    print(f"[{i}/{len(to_rerender)}] Post #{post.id} ({post.archetype}) — {post.title or '(no title)'}")
    try:
        result = orch.render_image_for_post(post.id, force=True)
        if result:
            print(f"  ✓ {result}")
        else:
            print(f"  ✗ Failed (no payload_json?)")
    except Exception as e:
        print(f"  ✗ Error: {e}")

db.close()
print("\nDone.")
