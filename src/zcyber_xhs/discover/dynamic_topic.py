"""Dynamic topic generator — LLM creates fresh TopicEntry objects on demand.

Instead of relying solely on static YAML banks (which exhaust and produce
repetitive content), this module asks the LLM to synthesise a novel,
timely topic for any archetype.  The YAML bank is loaded only to provide
3 format-reference examples so the LLM knows the expected field structure.
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

from ..models import TopicEntry

if TYPE_CHECKING:
    from ..generate.llm import LLMClient


# One-line description fed to the LLM so it understands the creative goal.
ARCHETYPE_DESCRIPTIONS: dict[str, str] = {
    "problem_command": (
        "A common, relatable security problem non-professionals encounter "
        "plus ONE terminal command that fixes or diagnoses it."
    ),
    "everyday_panic": (
        "A scary but relatable security moment (wrong Wi-Fi, suspicious login "
        "alert, phone got hot). Validate the fear, give a fast practical fix."
    ),
    "news_hook": (
        "A real CVE, data breach, or attack campaign making headlines right now. "
        "Tie breaking news to practical advice the audience can act on today."
    ),
    "mythbust": (
        "A common cybersecurity myth that non-technical people genuinely believe. "
        "State the myth clearly, then debunk it with a specific fact or example."
    ),
    "real_story": (
        "A humanised breach narrative — a vivid, specific story of how a real "
        "person or company got hacked. 3rd-person storytelling, then the lesson."
    ),
    "rank_war": (
        "A genuinely divisive security debate question with two clear opposing "
        "positions (e.g. 'VPN users vs no-VPN users'). Audience should feel "
        "compelled to pick a side and comment."
    ),
    "hacker_pov": (
        "Immersive 2nd-person POV — 'you are the attacker' scenario that walks "
        "through a real attack technique step-by-step, ending with the defender's "
        "counter-move."
    ),
}


class DynamicTopicGenerator:
    """Generate fresh TopicEntry objects via LLM instead of static YAML banks.

    Usage:
        gen = DynamicTopicGenerator(llm_client, config_dir)
        topic = gen.generate("rank_war")
    """

    def __init__(self, llm: "LLMClient", config_dir: Path):
        self.llm = llm
        self.banks_dir = config_dir / "topic_banks"

    def generate(self, archetype: str) -> Optional[TopicEntry]:
        """Generate a single fresh TopicEntry for the given archetype.

        Returns None if LLM call fails or JSON is invalid.
        """
        description = ARCHETYPE_DESCRIPTIONS.get(archetype, archetype)
        examples = self._load_examples(archetype, n=3)
        today = date.today().isoformat()

        prompt = self._build_prompt(archetype, description, examples, today)
        try:
            raw = self.llm.generate_json(prompt)
        except Exception:
            return None

        # Stamp a unique slug so it never collides with YAML bank slugs
        if not raw.get("slug"):
            rand_suffix = random.randint(100, 999)
            raw["slug"] = f"{archetype}-dynamic-{today}-{rand_suffix}"

        try:
            return TopicEntry(**raw)
        except Exception:
            return None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _load_examples(self, archetype: str, n: int = 3) -> list[dict]:
        """Return N random topics from the YAML bank as format-reference examples."""
        bank_file = self.banks_dir / f"{archetype}.yaml"
        if not bank_file.exists():
            return []
        with open(bank_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        topics = data.get("topics", [])
        if not topics:
            return []
        return random.sample(topics, min(n, len(topics)))

    @staticmethod
    def _build_prompt(
        archetype: str, description: str, examples: list[dict], today: str
    ) -> str:
        examples_block = json.dumps(examples, ensure_ascii=False, indent=2)
        return f"""You are a cybersecurity content strategist for Xiaohongshu (小红书), \
a Chinese short-video and image platform for non-technical audiences aged 18-35.

Today's date: {today}
Archetype: {archetype}
Goal: {description}

Your task: Generate ONE fresh, specific, timely topic object as valid JSON.

FORMAT REFERENCE — these are existing topics (do NOT reuse them, just copy their field structure):
{examples_block}

Hard requirements:
- Output a single valid JSON object only — no markdown, no explanation, no code fences
- Use the EXACT same field names as the examples above
- The "slug" field must be a unique kebab-case string (include year e.g. "wifi-evil-twin-2025")
- Be specific: reference real attack tools, CVEs from 2024-2025, real company names, real malware
- Angle toward what a non-professional Chinese user would find shocking, useful, or relatable
- Prioritise trending topics: AI-powered phishing, QR code scams, deepfake fraud, supply chain
  attacks, mobile spyware, credential stuffing, cloud misconfigs, social engineering via WeChat
- Vary the framing — avoid topics already covered by the format-reference examples above"""
