"""Comprehensive content safety filter for XHS account protection.

Three-layer defense:
  Layer 1: BLOCK — content that must never be published (exploits, creds, illegal)
  Layer 2: XHS COMPLIANCE — content that triggers XHS review/shadowban
  Layer 3: QUALITY GATE — content quality standards for brand protection

Runs post-LLM, pre-queue. If any Layer 1 check fails, content is rejected.
Layer 2 failures are also rejected (account protection > content).
Layer 3 issues generate warnings but don't block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════
# LAYER 1: HARD BLOCKS — dangerous content
# ═══════════════════════════════════════════════════════════

# Real credentials / secrets / tokens
CREDENTIAL_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI/Anthropic API key"),
    (r"ghp_[a-zA-Z0-9]{20,}", "GitHub PAT"),
    (r"gho_[a-zA-Z0-9]{20,}", "GitHub OAuth token"),
    (r"github_pat_[a-zA-Z0-9]{20,}", "GitHub fine-grained PAT"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"xox[bprs]-[a-zA-Z0-9\-]{10,}", "Slack token"),
    (r"glpat-[a-zA-Z0-9\-]{20,}", "GitLab PAT"),
    (r"bearer\s+[a-zA-Z0-9\-_.]{30,}", "Bearer token"),
    (r"eyJ[a-zA-Z0-9\-_]{20,}\.[a-zA-Z0-9\-_]{20,}\.", "JWT token"),
    (r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", "Private key"),
    (r"-----BEGIN\s+CERTIFICATE-----", "SSL certificate"),
    (r"mongodb(\+srv)?://\w+:\w+@", "MongoDB connection string"),
    (r"postgres://\w+:\w+@", "PostgreSQL connection string"),
    (r"mysql://\w+:\w+@", "MySQL connection string"),
    (r"redis://:\w+@", "Redis connection string"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}:\w{6,}", "Email:password combo"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
    (r"ya29\.[0-9A-Za-z\-_]+", "Google OAuth token"),
    (r"sk_live_[0-9a-zA-Z]{24,}", "Stripe live key"),
    (r"rk_live_[0-9a-zA-Z]{24,}", "Stripe restricted key"),
    (r"sq0atp-[0-9A-Za-z\-_]{22,}", "Square access token"),
    (r"AC[a-z0-9]{32}", "Twilio account SID"),
    (r"SG\.[a-zA-Z0-9\-_]{22,}\.[a-zA-Z0-9\-_]{22,}", "SendGrid API key"),
    (r"hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[a-zA-Z0-9]+", "Slack webhook"),
]

# Real public IPs (exclude private, loopback, doc ranges, link-local)
REAL_IP_PATTERN = re.compile(
    r"\b(?!192\.0\.2\.)(?!198\.51\.100\.)(?!203\.0\.113\.)"  # RFC5737 doc ranges
    r"(?!192\.168\.)(?!10\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"  # private
    r"(?!127\.)(?!0\.)(?!255\.)"  # loopback/unspecified/broadcast
    r"(?!100\.64\.)"  # CGNAT
    r"(?!169\.254\.)"  # link-local
    r"(?!224\.)"  # multicast
    r"(\d{1,3}\.){3}\d{1,3}\b"
)

# Exploit frameworks / C2 / active attack tools
EXPLOIT_PATTERNS = [
    (r"msfvenom\b", "Metasploit payload generator"),
    (r"msfconsole\b", "Metasploit console"),
    (r"meterpreter\b", "Meterpreter shell"),
    (r"cobalt\s*strike\b", "Cobalt Strike C2"),
    (r"empire\b.*stager", "Empire C2 stager"),
    (r"reverse.{0,10}shell", "Reverse shell"),
    (r"bind.{0,10}shell", "Bind shell"),
    (r"exploit/\w+/\w+", "Metasploit exploit module"),
    (r"payload/\w+/\w+", "Metasploit payload module"),
    (r"/bin/sh\s*-i", "Interactive shell spawn"),
    (r"nc\s+-e\s+/bin/", "Netcat shell execution"),
    (r"bash\s+-i\s+>&\s*/dev/tcp", "Bash reverse shell"),
    (r"python\s+-c\s+['\"]import\s+socket.*connect", "Python reverse shell"),
    (r"perl\s+-e\s+['\"].*socket.*INET", "Perl reverse shell"),
    (r"powershell.*-e(nc|ncodedcommand)\s+", "PowerShell encoded command"),
    (r"certutil.*-urlcache.*-split.*-f", "Certutil download cradle"),
    (r"bitsadmin.*/transfer", "Bitsadmin download"),
    (r"Invoke-(WebRequest|Expression|Shellcode)", "PowerShell malicious cmdlet"),
    (r"mimikatz", "Credential dumping tool"),
    (r"sekurlsa::logonpasswords", "Mimikatz credential dump"),
    (r"lazagne\b", "Password recovery/dump tool"),
    (r"rubeus\b", "Kerberos attack tool"),
    (r"impacket.*secretsdump", "Impacket credential dump"),
    (r"evil-winrm\b", "Evil-WinRM lateral movement"),
    (r"chisel\b.*tunnel", "Chisel tunneling tool"),
    (r"ngrok\b.*tcp", "Ngrok tunnel for C2"),
    (r"socat\b.*exec", "Socat shell execution"),
]

# Malware / ransomware indicators
MALWARE_PATTERNS = [
    (r"ransomware.*encrypt.*decrypt", "Ransomware description"),
    (r"keylog(ger|ging)", "Keylogger reference"),
    (r"rootkit\b.*install", "Rootkit installation"),
    (r"botnet\b.*command", "Botnet C2 reference"),
    (r"rat\b.*remote\s*access\s*trojan", "RAT reference"),
    (r"privilege\s*escalation\s*exploit", "Priv-esc exploit"),
    (r"zero.?day\s*(exploit|vulnerability|0day)", "Zero-day exploit"),
    (r"CVE-\d{4}-\d{4,}\s*(exploit|poc|proof)", "CVE exploit/PoC"),
]

# ═══════════════════════════════════════════════════════════
# LAYER 2: XHS COMPLIANCE — account protection
# ═══════════════════════════════════════════════════════════

# Terms that trigger XHS content review or account restriction
XHS_BANNED_TERMS = [
    # Circumvention / illegal access
    (r"翻墙", "VPN/circumvention"),
    (r"科学上网", "VPN/circumvention"),
    (r"梯子", "VPN/circumvention (slang)"),
    (r"机场", "VPN service (slang)"),  # in proxy/VPN context
    (r"代理.*节点", "Proxy nodes"),
    (r"SS[Rr]?\s*(节点|链接|订阅)", "Shadowsocks references"),
    (r"[Vv]2[Rr]ay", "V2Ray proxy"),
    (r"[Cc]lash\s*(配置|节点|订阅)", "Clash proxy config"),
    (r"trojan\s*(节点|链接|协议)", "Trojan proxy"),

    # Piracy / copyright violation
    (r"破解版", "Cracked software"),
    (r"盗版", "Pirated content"),
    (r"注册机", "Keygen"),
    (r"序列号.*生成", "Serial number generator"),
    (r"激活码.*免费", "Free activation codes"),
    (r"绿色版", "Portable/cracked software"),

    # Politically sensitive
    (r"黄赌毒", "Illegal content categories"),
    (r"颠覆.*政权", "Subversion"),
    (r"法轮功", "Banned organization"),
    (r"六四", "Politically sensitive date"),
    (r"天安门.*事件", "Politically sensitive event"),

    # Violence / terrorism
    (r"恐怖.*袭击.*教程", "Terrorism instruction"),
    (r"炸弹.*制作", "Bomb making"),
    (r"枪支.*购买", "Weapons purchase"),

    # Fraud / scams
    (r"洗钱", "Money laundering"),
    (r"电信诈骗.*教程", "Scam instruction"),
    (r"杀猪盘", "Romance scam"),
    (r"刷单", "Fake reviews/orders"),

    # Hacking-as-a-service
    (r"接单.*黑客", "Hacking service"),
    (r"代.*入侵", "Intrusion service"),
    (r"出售.*漏洞", "Selling vulnerabilities"),
    (r"出售.*数据库", "Selling databases"),
    (r"社工库", "Social engineering database"),
    (r"查开房", "Privacy violation service"),
    (r"人肉搜索", "Doxxing"),
]

# XHS shadowban triggers (content patterns the algorithm penalizes)
XHS_SHADOWBAN_TRIGGERS = [
    (r"(https?://[^\s]+){3,}", "Too many external links (3+)"),
    (r"(私信|私我|加我|加微信|wx:|vx:)", "Private traffic diversion"),
    (r"(微信号|QQ号|手机号)\s*[:：]?\s*\d", "Contact info sharing"),
    (r"(关注.*领取|点赞.*抽奖|转发.*免费)", "Engagement bait"),
    (r"(#[^\s#]+\s*){8,}", "Excessive hashtags (8+)"),
    (r"(赚钱|副业|收入|月入)\s*\d+", "Income claims"),
]

# ═══════════════════════════════════════════════════════════
# LAYER 3: QUALITY GATE — brand protection
# ═══════════════════════════════════════════════════════════

# Offensive tools that MUST have a safety disclaimer
OFFENSIVE_TOOLS = {
    "hydra", "hashcat", "john", "john the ripper",
    "fcrackzip", "pdfcrack", "office2john",
    "aircrack", "aircrack-ng", "aireplay",
    "sqlmap", "burpsuite", "burp suite",
    "nmap --script vuln", "nmap -sV --script",
    "nikto", "gobuster", "dirb", "dirsearch",
    "wfuzz", "ffuf",
    "responder", "bloodhound",
    "crackmapexec", "cme",
    "wpscan", "nuclei",
    "subfinder", "amass",
    "masscan",
    "theharvester",
    "recon-ng",
    "shodan",
}

# Minimum quality thresholds
MIN_BODY_LENGTH = 100
MIN_TITLE_LENGTH = 5
MAX_TITLE_LENGTH = 50
MIN_TAGS = 3
MAX_TAGS = 10
MAX_BODY_LENGTH = 2000


@dataclass
class SafetyResult:
    """Result of a safety check."""

    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    auto_fixes: list[str] = field(default_factory=list)
    severity: str = "ok"  # ok, warning, blocked

    def add_block(self, reason: str, category: str = "") -> None:
        prefix = f"[{category}] " if category else ""
        self.blocks.append(f"{prefix}{reason}")
        self.passed = False
        self.severity = "blocked"

    def add_warning(self, reason: str, category: str = "") -> None:
        prefix = f"[{category}] " if category else ""
        self.warnings.append(f"{prefix}{reason}")
        if self.severity == "ok":
            self.severity = "warning"


def check_content(
    title: str,
    body: str,
    tags: list[str],
    safety_disclaimer_needed: bool = False,
    safety_disclaimer: str = "",
) -> SafetyResult:
    """Run all three safety layers on generated content."""
    result = SafetyResult()
    full_text = f"{title}\n{body}\n{' '.join(tags)}"
    body_lower = body.lower()

    # ── Layer 1: Hard blocks ─────────────────────────────

    # 1a. Credentials / secrets
    for pattern, desc in CREDENTIAL_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            result.add_block(f"Real {desc} detected", "CRED")

    # 1b. Exploit / C2 patterns
    for pattern, desc in EXPLOIT_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            result.add_block(f"{desc} detected", "EXPLOIT")

    # 1c. Malware / ransomware patterns
    for pattern, desc in MALWARE_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            result.add_block(f"{desc}", "MALWARE")

    # 1d. Real public IP addresses (block, not just warn)
    real_ips = REAL_IP_PATTERN.findall(full_text)
    if real_ips:
        result.add_block(
            f"{len(real_ips)} real public IP address(es) found — "
            "use private IPs (192.168.x.x, 10.x.x.x) or example.com",
            "IP",
        )

    # 1e. Real domains that look like attack targets
    _check_suspicious_domains(full_text, result)

    # ── Layer 2: XHS compliance ──────────────────────────

    # 2a. Banned terms
    for pattern, desc in XHS_BANNED_TERMS:
        if re.search(pattern, full_text):
            result.add_block(f"XHS banned: {desc} ({pattern})", "XHS")

    # 2b. Shadowban triggers
    for pattern, desc in XHS_SHADOWBAN_TRIGGERS:
        if re.search(pattern, full_text):
            result.add_block(f"Shadowban risk: {desc}", "XHS")

    # 2c. Check for excessive self-promotion / external links
    url_count = len(re.findall(r"https?://", full_text))
    if url_count > 2:
        result.add_block(f"Too many URLs ({url_count}) — XHS penalizes this", "XHS")

    # 2d. Check for competitor platform mentions
    _check_platform_mentions(full_text, result)

    # ── Layer 3: Quality gate ────────────────────────────

    # 3a. Body length
    if len(body) < MIN_BODY_LENGTH:
        result.add_warning(f"Body too short ({len(body)} chars, min {MIN_BODY_LENGTH})", "QUALITY")
    if len(body) > MAX_BODY_LENGTH:
        result.add_warning(f"Body too long ({len(body)} chars, max {MAX_BODY_LENGTH})", "QUALITY")

    # 3b. Title length
    if len(title) < MIN_TITLE_LENGTH:
        result.add_warning(f"Title too short ({len(title)} chars)", "QUALITY")
    if len(title) > MAX_TITLE_LENGTH:
        result.add_warning(
            f"Title too long ({len(title)} chars, max {MAX_TITLE_LENGTH})", "QUALITY"
        )

    # 3c. Tags
    if len(tags) < MIN_TAGS:
        result.add_warning(f"Too few tags ({len(tags)}, min {MIN_TAGS})", "QUALITY")
    if len(tags) > MAX_TAGS:
        result.add_warning(f"Too many tags ({len(tags)}, max {MAX_TAGS})", "QUALITY")

    # 3d. Safety disclaimer for offensive tools
    if safety_disclaimer_needed and safety_disclaimer:
        if safety_disclaimer not in body:
            result.auto_fixes.append("safety_disclaimer_appended")

    # 3e. Check offensive tool mentions need disclaimer
    if not safety_disclaimer_needed:
        for tool in OFFENSIVE_TOOLS:
            if tool.lower() in body_lower:
                result.add_warning(
                    f"Offensive tool '{tool}' mentioned but safety_disclaimer_needed=false",
                    "DISCLAIMER",
                )
                result.auto_fixes.append("safety_disclaimer_forced")
                break

    # 3f. Repetitive content check (same phrase repeated 3+ times)
    _check_repetition(body, result)

    # 3g. All-caps / excessive punctuation (looks spammy)
    exclamation_count = body.count("!") + body.count("！")
    if exclamation_count > 8:
        result.add_warning(
            f"Too many exclamation marks ({exclamation_count}) — looks spammy", "QUALITY"
        )

    return result


def check_and_fix(
    title: str,
    body: str,
    tags: list[str],
    safety_disclaimer_needed: bool = False,
    safety_disclaimer: str = "",
) -> tuple[SafetyResult, str]:
    """Check content and apply auto-fixes to body."""
    result = check_content(title, body, tags, safety_disclaimer_needed, safety_disclaimer)
    fixed_body = body

    # Auto-fix: append safety disclaimer if missing or forced
    needs_disclaimer = safety_disclaimer_needed or "safety_disclaimer_forced" in result.auto_fixes
    if needs_disclaimer and safety_disclaimer and safety_disclaimer not in body:
        fixed_body = fixed_body.rstrip() + f"\n\n⚠️ {safety_disclaimer}"
        if "safety_disclaimer_appended" not in result.auto_fixes:
            result.auto_fixes.append("safety_disclaimer_appended")

    # Auto-fix: strip any accidental URLs beyond 2
    url_matches = list(re.finditer(r"https?://[^\s]+", fixed_body))
    if len(url_matches) > 2:
        # Keep first 2, remove the rest
        for match in reversed(url_matches[2:]):
            fixed_body = fixed_body[:match.start()] + fixed_body[match.end():]
        result.auto_fixes.append("excess_urls_stripped")

    # Auto-fix: trim excessive tags
    # (caller handles tags, this is just for reporting)

    return result, fixed_body


# ═══════════════════════════════════════════════════════════
# Helper checks
# ═══════════════════════════════════════════════════════════


def _check_suspicious_domains(text: str, result: SafetyResult) -> None:
    """Check for real domains that look like attack targets."""
    # Allow common safe/example domains
    safe_domains = {
        "example.com", "example.org", "example.net",
        "test.com", "localhost", "httpbin.org",
        "zcybernews.com", "zcybernews",
        "virustotal.com", "any.run",
        "haveibeenpwned.com",
        "github.com", "google.com",
        "cloudflare-dns.com",
    }

    # Find all domains in text
    domain_pattern = re.compile(
        r"\b([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\."
        r"(com|net|org|io|cn|gov|edu|mil|xyz|top|info|biz))\b"
    )

    for match in domain_pattern.finditer(text):
        domain = match.group(0).lower()
        if domain not in safe_domains and not domain.endswith(".example.com"):
            # Allow if it's clearly in an educational/reference context
            # But flag if it looks like a specific target
            result.add_warning(
                f"Real domain '{domain}' — ensure it's not a real attack target",
                "DOMAIN",
            )


def _check_platform_mentions(text: str, result: SafetyResult) -> None:
    """XHS penalizes mentions of competitor platforms."""
    competitors = [
        (r"抖音", "Douyin/TikTok"),
        (r"快手", "Kuaishou"),
        (r"B站|bilibili|哔哩哔哩", "Bilibili"),
        (r"微博", "Weibo"),
        (r"淘宝|天猫", "Taobao/Tmall"),
        (r"拼多多", "Pinduoduo"),
        (r"京东", "JD.com"),
    ]
    for pattern, name in competitors:
        if re.search(pattern, text, re.IGNORECASE):
            result.add_warning(
                f"Competitor platform '{name}' mentioned — may reduce XHS reach",
                "XHS",
            )


def _check_repetition(body: str, result: SafetyResult) -> None:
    """Check for repetitive phrases (spam signal)."""
    # Split into sentences and check for duplicates
    sentences = re.split(r"[。！？\n]", body)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    seen = {}
    for s in sentences:
        key = s[:30]  # first 30 chars as signature
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 3:
            result.add_warning("Repetitive content detected (same phrase 3+ times)", "QUALITY")
            return
