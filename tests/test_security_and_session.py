import json

from security.security_manager import SecurityManager
from security.session_manager import SessionManager


def test_session_manager_encrypts_json_cookies_without_pickle(tmp_path):
    sess_file = tmp_path / "sessions.json"
    key_file = tmp_path / "session.key"
    mgr = SessionManager(session_file=str(sess_file), key_file=str(key_file))

    mgr.create_session("bot_acc", "super_secret_pw", "friend_acc", "s1")
    session = mgr.get_session("s1")
    assert session is not None
    assert session["password"] == "super_secret_pw"

    # Kiểm tra file JSON lưu trên đĩa không lộ plaintext password
    raw_disk = json.loads(sess_file.read_text(encoding="utf-8"))
    assert raw_disk["s1"]["password"] != "super_secret_pw"

    cookies = [{"name": "sessionid", "value": "abc123", "domain": ".instagram.com"}]
    assert mgr.save_chrome_cookies("s1", cookies) is True

    reloaded = SessionManager(session_file=str(sess_file), key_file=str(key_file))
    loaded_cookies = reloaded.load_chrome_cookies("s1")
    assert loaded_cookies == cookies


def test_session_manager_cooldown_and_login_attempts(tmp_path):
    mgr = SessionManager(
        session_file=str(tmp_path / "s.json"), key_file=str(tmp_path / "k.key")
    )
    mgr.create_session("u", "p", "t", "sess")

    assert mgr.can_attempt_login("sess", max_attempts=2)[0] is True
    mgr.record_login_attempt("sess", success=False)
    mgr.record_login_attempt("sess", success=False)
    can_login, reason = mgr.can_attempt_login("sess", max_attempts=2, cooldown_minutes=15)
    assert can_login is False
    assert "cooldown" in reason.lower()

    mgr.set_account_cooldown("sess", minutes=10, reason="checkpoint")
    in_cd, cd_msg = mgr.is_in_cooldown("sess")
    assert in_cd is True
    assert "checkpoint" in cd_msg


def test_security_manager_spam_and_outbound_budget():
    sec = SecurityManager()
    ok, _ = sec.validate_message("Chào bạn, hôm nay thế nào?", "user1")
    assert ok is True

    # Spam có link + pattern lừa đảo
    bad_ok, bad_reason = sec.validate_message("FREE MONEY CLICK https://evil.example NOW", "spammer")
    assert bad_ok is False
    assert "spam" in bad_reason.lower()

    # Outbound safety budget kiểm soát khoảng nghỉ tối thiểu & trần mỗi phút
    base = 1000.0
    assert sec.check_outbound_budget("acct1", now=base)[0] is True
    sec.record_outbound_action("acct1", now=base)

    # Ngay sau 1 giây (< min_seconds_between_replies=4.0) phải chặn
    allowed_fast, fast_msg = sec.check_outbound_budget("acct1", now=base + 1.0)
    assert allowed_fast is False
    assert "nghỉ" in fast_msg.lower()

    # Sau 5 giây được phép gửi tiếp cho đến khi chạm giới hạn phút (mặc định 6)
    for step in range(1, 6):
        t = base + step * 5.0
        assert sec.check_outbound_budget("acct1", now=t)[0] is True
        sec.record_outbound_action("acct1", now=t)

    allowed_7th, msg_7th = sec.check_outbound_budget("acct1", now=base + 30.0)
    assert allowed_7th is False
    assert "phút" in msg_7th.lower()
