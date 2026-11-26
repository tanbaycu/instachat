import json
import urllib.request

from app import Listener
from dashboard.server import DashboardServer
import start_bot


def test_listener_echo_and_duplicate_suppression():
    listener = Listener(
        username="bot_user",
        password="pw",
        target_username="friend",
        skip_browser=True,
        start_thread=False,
    )
    listener.message_inited = True

    listener.sent_messages.append(("Mình vừa nhận được tin nhắn rồi nè!", 1e12))
    listener.last_sent_message = "Mình vừa nhận được tin nhắn rồi nè!"
    listener.last_sent_time = 1e12

    assert listener.is_bot_message("Mình vừa nhận được tin nhắn rồi nè!") is True
    assert listener.is_bot_message("Tin nhắn từ người dùng") is False

    assert listener.is_system_noise("Seen") is True
    assert listener.is_system_noise("Đã xem lúc 10:30") is True
    assert listener.is_system_noise("Active 5m ago") is True
    assert listener.is_system_noise("Đang nhập...") is True
    assert listener.is_system_noise("Xin chào bot!") is False

    listener.current_message_input = "Xin chào bot!"
    first = listener.listen_new_message()
    assert first == "Xin chào bot!"

    # Lần gọi kế tiếp với cùng nội dung không được trả lại nữa
    assert listener.listen_new_message() is None
    assert listener.is_duplicate_message("Xin chào bot!") is True


def test_dashboard_server_http_endpoints_and_sandbox(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-gemini-key-for-redaction-test")
    monkeypatch.setenv("INSTAGRAM_PASSWORD", "super-secret-ig-pass")

    server = DashboardServer(host="127.0.0.1", port=0)
    server.set_runtime_state(running=True, mode="test", active_account="demo_bot")
    server.start()

    try:
        with urllib.request.urlopen(f"{server.base_url}/", timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert "InstaChat v2.0 Console" in html

        with urllib.request.urlopen(f"{server.base_url}/health", timeout=5) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            assert health["status"] == "healthy"
            assert health["version"] == "2.0.0"

        with urllib.request.urlopen(f"{server.base_url}/api/overview", timeout=5) as resp:
            overview = json.loads(resp.read().decode("utf-8"))
            assert overview["runtime"]["mode"] == "test"
            assert overview["runtime"]["paused"] is False
            assert "outbound_budget" in overview
            assert "memory" in overview

        with urllib.request.urlopen(f"{server.base_url}/api/config", timeout=5) as resp:
            raw_cfg = resp.read().decode("utf-8")
            assert "secret-gemini-key-for-redaction-test" not in raw_cfg
            assert "super-secret-ig-pass" not in raw_cfg
            cfg_data = json.loads(raw_cfg)
            assert cfg_data["ai"]["api_key"] == "***"
            assert cfg_data["app"]["instagram_password"] == "***"

        with urllib.request.urlopen(f"{server.base_url}/api/analytics", timeout=5) as resp:
            analytics_data = json.loads(resp.read().decode("utf-8"))
            assert "summary" in analytics_data

        pause_req = urllib.request.Request(
            f"{server.base_url}/api/control/pause", data=b"", method="POST"
        )
        with urllib.request.urlopen(pause_req, timeout=5) as resp:
            assert json.loads(resp.read().decode("utf-8"))["paused"] is True

        resume_req = urllib.request.Request(
            f"{server.base_url}/api/control/resume", data=b"", method="POST"
        )
        with urllib.request.urlopen(resume_req, timeout=5) as resp:
            assert json.loads(resp.read().decode("utf-8"))["paused"] is False

        with urllib.request.urlopen(f"{server.base_url}/api/notifications", timeout=5) as resp:
            notifs = json.loads(resp.read().decode("utf-8"))
            assert "notifications" in notifs

        # Xóa GEMINI_API_KEY để test nhánh demo sandbox
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        req = urllib.request.Request(
            f"{server.base_url}/api/sandbox/chat",
            data=json.dumps({"message": "hello sandbox", "username": "qa_user"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            chat_res = json.loads(resp.read().decode("utf-8"))
            assert chat_res["mode"] == "demo"
            assert "hello sandbox" in chat_res["reply"]
    finally:
        server.stop()


def test_start_bot_cli_check_mode():
    exit_code = start_bot.main(["--mode", "check", "--skip-install"])
    assert exit_code == 0
