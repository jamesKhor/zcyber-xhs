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
    # ── Threat / awareness archetypes ────────────────────────────────────
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
    # ── Career / education archetypes (XHS pivot) ────────────────────────
    "cert_war": (
        "Head-to-head comparison of two cybersecurity certifications for an "
        "audience trying to choose which cert to pursue. Use real costs, real "
        "salary impact data, and give a clear verdict. Audience: 18-35 Chinese "
        "speakers considering or early in a cybersec career."
    ),
    "salary_map": (
        "A salary reveal carousel showing real pay bands (entry/mid/senior) for "
        "a specific cybersec role in a specific market (SG, MY, CN, AU, HK). "
        "Use shocking_fact as the hook. Aspirational tone — this is what you "
        "could earn, and here's how to get there."
    ),
    "career_entry": (
        "A practical, step-by-step roadmap for someone from a specific background "
        "breaking into cybersecurity in a specific market. Give a realistic "
        "timeline, first cert to get, free learning resources, and expected "
        "starting salary. Tone: senior colleague giving real advice, not a "
        "marketing pitch."
    ),
}


# Per-archetype category wheels — balanced distribution prevents theme repetition.
# Keep AI scams as just one entry among many.
ARCHETYPE_CATEGORIES: dict[str, list[str]] = {
    "everyday_panic": [
        "账号被盗/异常登录告警",
        "WiFi安全/公共网络风险",
        "设备安全/摄像头麦克风异常",
        "手机App权限/数据隐私",
        "邮件/短信钓鱼识别",
        "支付安全/转账风险",
        "社会工程学/冒充身份",
        "AI诈骗/语音视频伪造",
        "密码/2FA安全事故",
        "设备入侵/恶意软件迹象",
    ],
    "problem_command": [
        "网络侦察/端口扫描 (nmap, ss, netstat)",
        "进程/系统监控 (ps, top, lsof)",
        "文件取证/哈希校验 (strings, file, sha256sum)",
        "密码恢复 (fcrackzip, pdfcrack)",
        "日志分析/入侵痕迹 (last, auth.log, journalctl)",
        "DNS/域名查询 (dig, whois, host)",
        "SSL/证书检查 (openssl, curl)",
        "隐藏文件/权限检查 (find, ls -la, stat)",
        "网络流量分析 (tcpdump, wireshark basics)",
        "应急响应第一步 (隔离、快照、证据保留)",
    ],
    "mythbust": [
        "VPN神话",
        "防病毒软件局限",
        "HTTPS≠安全",
        "公司内网=安全",
        "强密码=安全",
        "iOS比Android安全",
        "黑客都是天才/技术高手",
        "删除=彻底消失",
        "小网站不会被黑",
        "2FA万能",
    ],
    "real_story": [
        "供应链攻击",
        "内鬼威胁/离职员工",
        "钓鱼邮件成功案例",
        "勒索软件攻击",
        "API密钥泄露",
        "社会工程学成功案例",
        "云配置错误",
        "默认凭证被利用",
        "SQL注入实例",
        "OAuth劫持",
    ],
    "rank_war": [
        "VPN vs 无VPN",
        "密码管理器 vs 记在脑子里",
        "iPhone vs Android安全性",
        "公司设备 vs 个人设备办公",
        "双因素验证 vs 长密码",
        "云备份 vs 本地备份",
        "杀毒软件 vs 不装杀毒",
        "开源软件 vs 商业软件",
    ],
    "hacker_pov": [
        "钓鱼攻击/Vishing",
        "撞库攻击/Credential Stuffing",
        "供应链投毒/npm恶意包",
        "Wi-Fi中间人/Evil Twin",
        "API密钥泄露/Git扫描",
        "社会工程学/冒充IT",
        "勒索软件植入过程",
        "SQL注入真实流程",
        "OAuth Token盗取",
        "DNS劫持/BGP劫持",
    ],
    "news_hook": [
        "CVE高危漏洞",
        "大规模数据泄露",
        "勒索软件攻击事件",
        "供应链攻击新闻",
        "AI滥用安全威胁",
        "国家级APT攻击",
        "零日漏洞利用",
        "硬件安全漏洞",
        "IoT设备被控",
        "云服务配置泄露",
    ],
    # ── Career archetypes ─────────────────────────────────────────────────
    "cert_war": [
        "入门证书对决 (Security+ vs eJPT)",
        "渗透测试证书 (OSCP vs CEH vs PNPT)",
        "管理层证书 (CISSP vs CISM)",
        "国产vs国际 (CISP vs CISSP)",
        "中国本土证书 (CISP vs CISAW)",
        "中国渗透证书 (CISP-PTE vs OSCP)",
        "蓝队证书 (GCIH vs CySA+)",
        "新加坡市场证书排行",
        "中国市场证书排行",
        "证书ROI分析/性价比",
        "云安全证书 (AWS Security vs CISSP)",
        "等级保护测评师现实评测",
    ],
    "salary_map": [
        "新加坡薪资 (SOC/渗透/云安全)",
        "马来西亚薪资 (KL市场)",
        "中国T1城市薪资 (北上深)",
        "中国T2城市薪资 (成都/杭州/南京)",
        "澳大利亚薪资 (悉尼/墨尔本)",
        "香港薪资 (HKD)",
        "跨市场对比 (SG vs AU vs HK)",
        "甲方vs乙方vs大厂薪资对比",
        "入门级全球对比 (哪个市场最友好)",
        "高级职位薪资天花板",
        "远程工作薪资套利",
        "CISO薪资揭秘",
    ],
    "career_entry": [
        "CS/IT应届生入行路径",
        "非技术背景转GRC分析师",
        "开发者转AppSec工程师",
        "IT运维转云安全",
        "军警背景转网安 (SG/AU)",
        "30岁+中途转行",
        "中国fresh grad甲方vs乙方首选",
        "零预算自学路径 (TryHackMe+HTB)",
        "澳大利亚移民签证+网安路径",
        "等级保护测评师另类入口",
        "Bug Bounty入行timeline",
        "蓝队vs红队哪个更容易入行",
        "新加坡DSTA/政府路径",
        "东南亚bootcamp vs 自学ROI",
    ],
}


class DynamicTopicGenerator:
    """Generate fresh TopicEntry objects via LLM instead of static YAML banks.

    Usage:
        gen = DynamicTopicGenerator(llm_client, config_dir)
        topic = gen.generate("rank_war")
        topic = gen.generate("everyday_panic", recent_titles=["ai-scam-wechat", "deepfake-boss"])
    """

    def __init__(self, llm: "LLMClient", config_dir: Path):
        self.llm = llm
        self.banks_dir = config_dir / "topic_banks"

    def generate(
        self, archetype: str, recent_titles: list[str] | None = None
    ) -> Optional[TopicEntry]:
        """Generate a single fresh TopicEntry for the given archetype.

        Args:
            archetype: The content archetype to generate for.
            recent_titles: Slugs/titles of recently generated topics to avoid
                repeating. Injected into the prompt as "AVOID these themes".

        Returns None if LLM call fails or JSON is invalid.
        """
        if recent_titles is None:
            recent_titles = []
        description = ARCHETYPE_DESCRIPTIONS.get(archetype, archetype)
        examples = self._load_examples(archetype, n=3)
        today = date.today().isoformat()

        prompt = self._build_prompt(
            archetype, description, examples, today, recent_titles
        )
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
        archetype: str,
        description: str,
        examples: list[dict],
        today: str,
        recent_titles: list[str],
    ) -> str:
        examples_block = json.dumps(examples, ensure_ascii=False, indent=2)
        categories = ARCHETYPE_CATEGORIES.get(archetype, [])
        categories_text = "\n".join(f"  - {c}" for c in categories)

        if recent_titles:
            recent_titles_text = "\n".join(f"  - {t}" for t in recent_titles)
        else:
            recent_titles_text = "  (none yet)"

        return f"""You are a cybersecurity content strategist for Xiaohongshu (小红书), \
a Chinese short-video and image platform for non-technical audiences aged 18-35.

Today's date: {today}
Archetype: {archetype}
Goal: {description}

Your task: Generate ONE fresh, specific, timely topic object as valid JSON.

FORMAT REFERENCE — these are existing topics (do NOT reuse them, just copy their field structure):
{examples_block}

Category wheel for {archetype} — pick from a category NOT in the recent topics list:
{categories_text}

Recent topics already covered (DO NOT generate anything in the same category or theme):
{recent_titles_text}

Pick a category from the wheel that is furthest from the recent topics, \
then generate a topic within it.

Hard requirements:
- Output a single valid JSON object only — no markdown, no explanation, no code fences
- Use the EXACT same field names as the examples above
- The "slug" field must be a unique kebab-case string (include year e.g. "wifi-evil-twin-2025")
- Be specific: reference real attack tools, CVEs from 2024-2025, real company names, real malware
- Angle toward what a non-professional Chinese user would find shocking, useful, or relatable
- Vary the framing — avoid topics already covered by the format-reference examples above"""
