"""Content safety filter — blocks dangerous content before it enters the queue.

Runs post-LLM, pre-queue. Catches:
- Real exploit code, C2 addresses, working payloads
- Actual credentials, API keys, private IPs/domains
- Missing safety disclaimers on offensive tool posts
- XHS-sensitive terms that could trigger account restrictions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Patterns that should NEVER appear in published content ──

# Real-looking API keys / tokens / passwords
CREDENTIAL_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",                # OpenAI/Anthropic-style keys
    r"ghp_[a-zA-Z0-9]{20,}",               # GitHub PAT
    r"AKIA[0-9A-Z]{16}",                    # AWS access key
    r"xox[bprs]-[a-zA-Z0-9\-]{10,}",       # Slack token
    r"glpat-[a-zA-Z0-9\-]{20,}",           # GitLab PAT
    r"bearer\s+[a-zA-Z0-9\-_.]{30,}",      # Bearer tokens
]

# Real IP addresses (non-RFC5737 documentation ranges)
REAL_IP_PATTERN = re.compile(
    r"\b(?!192\.0\.2\.)(?!198\.51\.100\.)(?!203\.0\.113\.)"  # exclude doc ranges
    r"(?!192\.168\.)(?!10\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"  # exclude private
    r"(?!127\.)(?!0\.)"  # exclude loopback/unspecified
    r"(?!100\.64\.)"  # exclude CGNAT
    r"(\d{1,3}\.){3}\d{1,3}\b"
)

# Known exploit frameworks / C2 indicators
EXPLOIT_PATTERNS = [
    r"msfvenom\b",
    r"msfconsole\b",
    r"meterpreter\b",
    r"cobalt\s*strike\b",
    r"reverse.{0,10}shell",
    r"bind.{0,10}shell",
    r"exploit/\w+/\w+",          # Metasploit module paths
    r"payload/\w+/\w+",
    r"/bin/sh\s*-i",             # Interactive shell spawning
    r"nc\s+-e\s+/bin/",         # Netcat reverse shell
    r"bash\s+-i\s+>&",          # Bash reverse shell
]

# Offensive tools that require a safety disclaimer
OFFENSIVE_TOOLS = {
    "hydra", "hashcat", "john", "fcrackzip", "pdfcrack",
    "aircrack", "sqlmap", "burpsuite", "metasploit",
    "nmap --script vuln", "nikto", "gobuster", "dirb",
    "wfuzz", "ffuf", "responder", "mimikatz", "bloodhound",
    "crackmapexec", "impacket", "evil-winrm",
}

# XHS-sensitive terms (could trigger content review)
XHS_SENSITIVE = [
    r"翻墙",
    r"科学上网",
    r"破解.*版权",
    r"盗版",
    r"黄赌毒",
]


@dataclass
class SafetyResult:
    """Result of a safety check."""

    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    auto_fixes: list[str] = field(default_factory=list)


def check_content(
    title: str,
    body: str,
    tags: list[str],
    safety_disclaimer_needed: bool = False,
    safety_disclaimer: str = "",
) -> SafetyResult:
    """Run all safety checks on generated content.

    Returns SafetyResult with pass/fail, warnings, blocks, and auto-fixes applied.
    """
    result = SafetyResult()
    full_text = f"{title}\n{body}\n{' '.join(tags)}"

    # 1. Check for real credentials
    for pattern in CREDENTIAL_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            result.blocks.append(f"Real credential pattern detected: {pattern}")
            result.passed = False

    # 2. Check for real public IP addresses
    real_ips = REAL_IP_PATTERN.findall(full_text)
    if real_ips:
        result.warnings.append(
            f"Possible real IP addresses found ({len(real_ips)} matches). "
            "Ensure these are examples, not real targets."
        )

    # 3. Check for exploit/C2 patterns
    for pattern in EXPLOIT_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            result.blocks.append(f"Exploit/C2 pattern detected: {pattern}")
            result.passed = False

    # 4. Check safety disclaimer for offensive tools
    if safety_disclaimer_needed and safety_disclaimer:
        if safety_disclaimer not in body:
            result.auto_fixes.append("safety_disclaimer_appended")

    # 5. Check for XHS-sensitive terms
    for pattern in XHS_SENSITIVE:
        if re.search(pattern, full_text):
            result.blocks.append(f"XHS-sensitive term detected: {pattern}")
            result.passed = False

    # 6. Basic quality checks
    if len(body) < 100:
        result.warnings.append("Body is very short (<100 chars)")
    if len(title) < 5:
        result.warnings.append("Title is very short (<5 chars)")
    if not tags:
        result.warnings.append("No tags provided")

    return result


def check_and_fix(
    title: str,
    body: str,
    tags: list[str],
    safety_disclaimer_needed: bool = False,
    safety_disclaimer: str = "",
) -> tuple[SafetyResult, str]:
    """Check content and apply auto-fixes to body. Returns (result, fixed_body)."""
    result = check_content(title, body, tags, safety_disclaimer_needed, safety_disclaimer)
    fixed_body = body

    # Auto-append safety disclaimer if missing
    if safety_disclaimer_needed and safety_disclaimer and safety_disclaimer not in body:
        fixed_body = fixed_body.rstrip() + f"\n\n⚠️ {safety_disclaimer}"

    return result, fixed_body
