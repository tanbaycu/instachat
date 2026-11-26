from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
from typing import Any, Dict, Optional

from analytics.analytics_engine import get_analytics_engine
from automation.proxy_manager import parse_proxy_url
from config.config_manager import get_config_manager
from memory.store import SQLiteMemoryStore
from monitoring.error_handler import get_error_handler
from monitoring.performance_monitor import get_performance_monitor
from security.security_manager import get_security_manager
from security.session_manager import get_session_manager
from utils.cache_manager import get_cache_manager
from utils.notification_system import get_notification_system

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_MAX_BODY_BYTES = 32 * 1024


class DashboardServer:
    """HTTP Telemetry Dashboard + Interactive Sandbox API thuần stdlib."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        bot: Any = None,
    ):
        self.host = host
        self.port = int(port)
        self._bot = bot
        self._controller: Any = None
        self._paused = False
        self._bot_lock = threading.Lock()
        self._runtime_lock = threading.RLock()
        self._started_at = time.time()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

        self.runtime_state: Dict[str, Any] = {
            "running": False,
            "mode": "standalone",
            "active_account": None,
            "targets": [],
            "proxy": "direct",
            "started_at": datetime.now().isoformat(),
        }

    def attach_bot(self, bot: Any) -> None:
        with self._bot_lock:
            self._bot = bot

    def attach_controller(self, controller: Any) -> None:
        """Gắn instance InstaChat để điều khiển Pause/Resume trực tiếp từ Dashboard."""
        with self._runtime_lock:
            self._controller = controller

    def set_paused(self, paused: bool) -> bool:
        with self._runtime_lock:
            self._paused = bool(paused)
            if self._controller is not None and hasattr(self._controller, "pause_event"):
                if self._paused:
                    self._controller.pause_event.set()
                else:
                    self._controller.pause_event.clear()
            return self._paused

    def is_paused(self) -> bool:
        with self._runtime_lock:
            if self._controller is not None and hasattr(self._controller, "pause_event"):
                return bool(self._controller.pause_event.is_set())
            return self._paused

    def set_runtime_state(self, **kwargs: Any) -> None:
        with self._runtime_lock:
            self.runtime_state.update(kwargs)

    @property
    def actual_port(self) -> int:
        if self._server is not None:
            return int(self._server.server_address[1])
        return self.port

    @property
    def base_url(self) -> str:
        display_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        return f"http://{display_host}:{self.actual_port}"

    def _get_or_init_sandbox_bot(self) -> Any:
        with self._bot_lock:
            if self._bot is not None:
                return self._bot

            api_key = os.getenv("GEMINI_API_KEY") or get_config_manager().get("ai", "api_key")
            if api_key and api_key != "your_gemini_api_key_here":
                from core import create_insta_bot

                self._bot = create_insta_bot(api_key=api_key)
                return self._bot
            return None

    def get_overview_payload(self) -> Dict[str, Any]:
        cfg = get_config_manager()
        perf = get_performance_monitor()
        sec = get_security_manager()
        sess = get_session_manager()
        analytics = get_analytics_engine()
        cache = get_cache_manager()
        errors = get_error_handler()

        memory_stats: Dict[str, Any]
        with self._bot_lock:
            bot_ref = self._bot
        if bot_ref is not None:
            memory_stats = bot_ref.memory_store.get_stats()
        else:
            store = SQLiteMemoryStore()
            try:
                memory_stats = store.get_stats()
            finally:
                store.close()

        with self._runtime_lock:
            runtime_copy = dict(self.runtime_state)
        runtime_copy["paused"] = self.is_paused()
        runtime_copy["uptime_seconds"] = round(time.time() - self._started_at, 1)

        ai_cfg = cfg.get("ai") or {}
        stealth_cfg = cfg.get("stealth") or {}
        account_key = runtime_copy.get("active_account") or "default"

        return {
            "version": "2.0.0",
            "runtime": runtime_copy,
            "ai": {
                "model": ai_cfg.get("model"),
                "image_model": ai_cfg.get("image_model"),
                "gemini_configured": bool(
                    (os.getenv("GEMINI_API_KEY") or ai_cfg.get("api_key"))
                    and (os.getenv("GEMINI_API_KEY") or ai_cfg.get("api_key")) != "your_gemini_api_key_here"
                ),
            },
            "stealth": {
                "enabled": bool(stealth_cfg.get("enabled", True)),
                "persistent_profile": bool(stealth_cfg.get("persistent_profile", True)),
                "human_typing": bool(stealth_cfg.get("human_typing", True)),
                "active_hours": (
                    f"{stealth_cfg.get('active_hours_start')}:00 - {stealth_cfg.get('active_hours_end')}:00"
                    if stealth_cfg.get("active_hours_start") is not None
                    and stealth_cfg.get("active_hours_end") is not None
                    else "24/7"
                ),
            },
            "performance": perf.get_current_stats(),
            "health": perf.get_health_status(),
            "outbound_budget": sec.get_outbound_budget_status(account_key),
            "security": sec.get_security_stats(),
            "sessions": sess.get_session_stats(),
            "memory": memory_stats,
            "analytics": analytics.generate_report(days=7)["summary"],
            "cache": cache.get_cache_stats(),
            "errors": errors.get_error_stats(),
        }

    def get_redacted_config(self) -> Dict[str, Any]:
        """Trả về cấu hình hiện tại đã ẩn toàn bộ mật khẩu, API key và thông tin nhạy cảm."""
        cfg = get_config_manager()
        result: Dict[str, Any] = {}
        for group in ("app", "ai", "security", "stealth", "proxy", "dashboard", "cache"):
            data = cfg.get(group) or {}
            if isinstance(data, dict):
                result[group] = dict(data)

        if "app" in result and result["app"].get("instagram_password"):
            result["app"]["instagram_password"] = "***"
        if "ai" in result and result["ai"].get("api_key"):
            result["ai"]["api_key"] = "***"
        if "proxy" in result:
            for key in ("url", "list"):
                raw_val = result["proxy"].get(key)
                if raw_val:
                    try:
                        result["proxy"][key] = parse_proxy_url(str(raw_val)).safe_url
                    except ValueError:
                        result["proxy"][key] = "***"
        return result

    def handle_sandbox_chat(self, message: str, username: str = "sandbox_user") -> Dict[str, Any]:
        start_ts = time.time()
        bot = self._get_or_init_sandbox_bot()
        if bot is not None:
            reply = bot.generate_response(message, username=username)
            return {
                "reply": reply,
                "mode": "gemini",
                "username": username,
                "latency_ms": round((time.time() - start_ts) * 1000.0, 1),
            }

        # Chế độ Demo an toàn khi chưa điền GEMINI_API_KEY
        sec = get_security_manager()
        valid, err = sec.validate_message(message, username)
        if not valid:
            return {
                "reply": f"[Security Filter] Tin nhắn bị từ chối: {err}",
                "mode": "demo",
                "username": username,
                "latency_ms": round((time.time() - start_ts) * 1000.0, 1),
            }
        sec.log_message(message, username, "demo_preview", "demo")
        return {
            "reply": (
                f"[Demo Sandbox] Đã nhận '{message}'. "
                "Hãy thiết lập GEMINI_API_KEY trong file .env để trò chuyện trực tiếp với Gemini AI."
            ),
            "mode": "demo",
            "username": username,
            "latency_ms": round((time.time() - start_ts) * 1000.0, 1),
        }

    def start(self) -> None:
        if self._server is not None:
            return

        dashboard_ref = self

        class RequestHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                # Ẩn log HTTP chi tiết để không làm nhiễu console của bot
                return

            def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html_bytes: bytes, status: int = HTTPStatus.OK) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
                self.wfile.write(html_bytes)

            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path == "/" or path == "/index.html":
                    index_file = os.path.join(_STATIC_DIR, "index.html")
                    if os.path.exists(index_file):
                        with open(index_file, "rb") as f:
                            self._send_html(f.read())
                    else:
                        self._send_json({"error": "Dashboard UI not found"}, HTTPStatus.NOT_FOUND)
                elif path == "/health":
                    self._send_json(
                        {
                            "status": "healthy",
                            "version": "2.0.0",
                            "uptime_seconds": round(time.time() - dashboard_ref._started_at, 1),
                        }
                    )
                elif path == "/api/overview":
                    self._send_json(dashboard_ref.get_overview_payload())
                elif path == "/api/config":
                    self._send_json(dashboard_ref.get_redacted_config())
                elif path == "/api/analytics":
                    self._send_json(get_analytics_engine().generate_report(days=7))
                elif path == "/api/notifications":
                    notifs = get_notification_system().get_recent_notifications(hours=24, limit=30)
                    self._send_json({"notifications": list(reversed(notifs))})
                else:
                    self._send_json({"error": "Not Found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                path = self.path.split("?")[0]
                if path == "/api/control/pause":
                    paused = dashboard_ref.set_paused(True)
                    self._send_json({"paused": paused})
                    return
                if path == "/api/control/resume":
                    paused = dashboard_ref.set_paused(False)
                    self._send_json({"paused": paused})
                    return
                if path != "/api/sandbox/chat":
                    self._send_json({"error": "Not Found"}, HTTPStatus.NOT_FOUND)
                    return

                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send_json({"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
                    return

                if content_length <= 0 or content_length > _MAX_BODY_BYTES:
                    self._send_json({"error": "Payload size out of bounds"}, HTTPStatus.BAD_REQUEST)
                    return

                try:
                    raw = self.rfile.read(content_length)
                    data = json.loads(raw.decode("utf-8"))
                except Exception:
                    self._send_json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
                    return

                message = str(data.get("message", "")).strip()
                if not message:
                    self._send_json({"error": "Field 'message' is required"}, HTTPStatus.BAD_REQUEST)
                    return

                username = str(data.get("username", "sandbox_user")).strip() or "sandbox_user"
                result = dashboard_ref.handle_sandbox_chat(message, username=username)
                self._send_json(result)

        self._server = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
