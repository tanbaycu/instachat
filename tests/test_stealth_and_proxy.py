from datetime import datetime
import json

from automation.driver_manager import AccountSafetyDetector, SafetyState
from automation.proxy_manager import (
    ProxyPool,
    create_chrome_proxy_auth_extension,
    parse_proxy_url,
)
from automation.stealth import BrowserFingerprint, HumanBehavior, build_chrome_options


def test_proxy_parsing_redaction_sticky_and_rotation(tmp_path):
    p1 = parse_proxy_url("http://user1:secretpass@10.0.0.1:8080")
    assert p1.requires_auth is True
    assert "secretpass" not in p1.safe_url
    assert p1.chrome_arg == "http://10.0.0.1:8080"

    p2 = parse_proxy_url("10.0.0.2:9090:u2:p2")
    assert p2.host == "10.0.0.2"
    assert p2.port == 9090
    assert p2.username == "u2"

    pool = ProxyPool(
        proxy_list="http://user1:secretpass@10.0.0.1:8080,socks5://10.0.0.3:1080",
        sticky_per_account=True,
    )
    first = pool.get_proxy_for_account("acct_a")
    second = pool.get_proxy_for_account("acct_a")
    assert first == second

    rotated = pool.rotate_proxy("acct_a")
    assert rotated is not None
    assert rotated.host != first.host
    assert "secretpass" not in json.dumps(pool.get_status())

    ext_dir = create_chrome_proxy_auth_extension(p1, str(tmp_path / "ext"))
    manifest = json.loads((tmp_path / "ext" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert "webRequestAuthProvider" in manifest["permissions"]
    assert ext_dir.endswith("ext")


def test_proxy_pool_get_healthy_proxy_failover(monkeypatch):
    pool = ProxyPool(
        proxy_list="http://10.0.0.1:8080,http://10.0.0.2:8080",
        sticky_per_account=True,
    )

    def fake_check_health(proxy, timeout=8.0, check_url=""):
        if proxy.host == "10.0.0.1":
            pool.mark_failed(proxy)
            return False, "timeout"
        pool.mark_healthy(proxy)
        return True, "203.0.113.10"

    monkeypatch.setattr(pool, "check_health", fake_check_health)
    chosen = pool.get_healthy_proxy("acct_x", check_health=True)
    assert chosen is not None
    assert chosen.host == "10.0.0.2"


def test_stealth_fingerprint_options_and_human_behavior():
    fp = BrowserFingerprint.generate_random()
    restored = BrowserFingerprint.from_dict(fp.to_dict())
    assert restored.viewport_width == fp.viewport_width
    assert restored.timezone == "Asia/Ho_Chi_Minh"

    opts = build_chrome_options(fp, headless=True, proxy_ext_dir="/tmp/fake_ext")
    assert "--disable-web-security" not in opts.arguments
    assert "--disable-extensions" not in opts.arguments
    assert any(arg.startswith("--load-extension=") for arg in opts.arguments)

    delay_short = HumanBehavior.calculate_reading_delay("hi")
    delay_long = HumanBehavior.calculate_reading_delay("a" * 200)
    assert delay_short >= 0.7
    assert delay_long > delay_short

    # Active hours bình thường (8 -> 22) và qua nửa đêm (22 -> 6)
    assert HumanBehavior.is_within_active_hours(8, 22, datetime(2026, 1, 1, 14, 0)) is True
    assert HumanBehavior.is_within_active_hours(8, 22, datetime(2026, 1, 1, 23, 0)) is False
    assert HumanBehavior.is_within_active_hours(22, 6, datetime(2026, 1, 1, 1, 30)) is True
    assert HumanBehavior.is_within_active_hours(22, 6, datetime(2026, 1, 1, 12, 0)) is False
    assert HumanBehavior.is_within_active_hours(None, None) is True


def test_account_safety_detector():
    state, _ = AccountSafetyDetector.inspect("https://www.instagram.com/direct/t/123/", "Hello")
    assert state == SafetyState.OK

    state, _ = AccountSafetyDetector.inspect("https://www.instagram.com/challenge/123/", "")
    assert state == SafetyState.CHALLENGE

    state, _ = AccountSafetyDetector.inspect("https://www.instagram.com/accounts/login/two_factor", "")
    assert state == SafetyState.TWO_FACTOR

    state, _ = AccountSafetyDetector.inspect(
        "https://www.instagram.com/", "Please wait a few minutes before you try again."
    )
    assert state == SafetyState.RATE_LIMITED

    state, _ = AccountSafetyDetector.inspect("https://www.instagram.com/accounts/suspended/", "")
    assert state == SafetyState.SUSPENDED
