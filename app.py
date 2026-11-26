from collections import deque
import hashlib
import os
import signal
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from analytics.analytics_engine import get_analytics_engine
from analytics.conversation_insights import get_conversation_insights
from automation.driver_manager import InstagramDriverManager, SafetyState
from automation.selectors import (
    COMPOSER_INPUT_XPATHS,
    DIRECT_INBOX_URL,
    DIRECT_THREAD_SEARCH_XPATHS,
    DISMISS_POPUP_XPATHS,
    FILE_UPLOAD_INPUT_XPATHS,
    MESSAGE_TEXT_XPATHS,
    PROFILE_MESSAGE_BUTTON_XPATHS,
    SYSTEM_NOISE_PATTERNS,
)
from automation.stealth import HumanBehavior
from config.config_manager import get_config_manager
from core import cleanup_insta_bot, create_insta_bot
from monitoring.error_handler import ErrorSeverity, get_error_handler
from monitoring.performance_monitor import get_performance_monitor
from security.security_manager import get_security_manager
from security.session_manager import get_session_manager
from utils.notification_system import (
    notify_critical,
    notify_error,
    notify_info,
    notify_warning,
)


class LoginCreateSession:
    """Quản lý vòng đời driver và điều hướng đến khung chat Instagram Direct."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        target_username: Optional[str] = None,
        user_temp_dir_path: Optional[str] = None,
        skip_browser: bool = False,
        driver_manager: Optional[InstagramDriverManager] = None,
    ):
        self.username = username or ""
        self.password = password or ""
        self.user_temp_dir_path = user_temp_dir_path
        self.target_username = (target_username or "").lstrip("@")

        self.config_manager = get_config_manager()
        self.session_manager = get_session_manager()
        self.security_manager = get_security_manager()
        self.error_handler = get_error_handler()
        self.session_name = f"session_{self.username}_{self.target_username}"

        self.driver_manager = driver_manager
        self.driver: Any = None

        if not skip_browser:
            if self.driver_manager is None:
                self.driver_manager = InstagramDriverManager(
                    username=self.username,
                    password=self.password,
                    target_username=self.target_username,
                    session_name=self.session_name,
                    config_manager=self.config_manager,
                    session_manager=self.session_manager,
                )
            self.driver = self.driver_manager.init_driver()
            self.driver_manager.login()
            if self.target_username:
                self.go_to_chat(self.target_username)

    def go_to_chat(self, target_username: Optional[str] = None) -> bool:
        target = (target_username or self.target_username).lstrip("@")
        if not self.driver or not target:
            return False

        self.target_username = target
        notify_info(f"Đang mở cuộc trò chuyện với @{target}...", "chat_nav")
        self.driver.get(f"https://www.instagram.com/{target}/")
        HumanBehavior.jittered_sleep(2.5, 0.3)

        click_message_btn = None
        for xpath in PROFILE_MESSAGE_BUTTON_XPATHS:
            try:
                click_message_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                break
            except Exception:
                continue

        if not click_message_btn:
            # Fallback: mở trực tiếp Instagram Direct inbox và tìm theo username nếu nút profile bị ẩn
            if not self._open_chat_via_direct_inbox(target):
                notify_warning(f"Không tìm thấy nút Message trên trang cá nhân @{target}", "chat_nav")
                return False
            return True

        try:
            click_message_btn.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", click_message_btn)

        HumanBehavior.jittered_sleep(2.0, 0.3)
        for xpath in DISMISS_POPUP_XPATHS:
            try:
                btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                btn.click()
                break
            except Exception:
                continue

        return True

    def _open_chat_via_direct_inbox(self, target: str) -> bool:
        if not self.driver:
            return False
        try:
            self.driver.get(DIRECT_INBOX_URL)
            HumanBehavior.jittered_sleep(2.0, 0.3)
            for xpath in DISMISS_POPUP_XPATHS:
                try:
                    btn = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    btn.click()
                    break
                except Exception:
                    continue

            thread_link = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//a[contains(@href, '/direct/t/') and contains(., '{target}')]")
                )
            )
            thread_link.click()
            return True
        except Exception:
            for xpath in DIRECT_THREAD_SEARCH_XPATHS:
                try:
                    search_box = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    search_box.clear()
                    HumanBehavior.human_type(self.driver, search_box, target)
                    HumanBehavior.jittered_sleep(1.5, 0.2)
                    result = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, f"//span[contains(text(), '{target}')]"))
                    )
                    result.click()
                    return True
                except Exception:
                    continue
        return False


class Listener(LoginCreateSession):
    """Lắng nghe tin nhắn đến an toàn đa luồng, chống echo và lọc trùng lặp."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        target_username: Optional[str] = None,
        user_temp_dir_path: Optional[str] = None,
        skip_browser: bool = False,
        start_thread: bool = True,
        driver_manager: Optional[InstagramDriverManager] = None,
    ):
        super().__init__(
            username=username,
            password=password,
            target_username=target_username,
            user_temp_dir_path=user_temp_dir_path,
            skip_browser=skip_browser,
            driver_manager=driver_manager,
        )
        self._state_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.safety_halt_reason: Optional[str] = None

        self.hist_message_input = ""
        self.current_message_input = ""
        self.message_inited = False

        self.processed_messages: Deque[str] = deque(maxlen=200)
        self.processed_set = set()
        self.sent_messages: Deque[Tuple[str, float]] = deque(maxlen=20)
        self.last_user_message = ""
        self.last_user_message_time = 0.0
        self.last_sent_message = ""
        self.last_sent_time = 0.0

        self.total_messages_processed = 0
        self.duplicate_detections = 0

        self.listener_thread: Optional[threading.Thread] = None
        if start_thread and not skip_browser:
            self.listener_thread = threading.Thread(target=self.listener, daemon=True)
            self.listener_thread.start()

    def create_message_hash(self, message: str, window_minutes: int = 2) -> str:
        time_window = int(time.time() // (window_minutes * 60))
        hash_input = f"{message.strip()}_{time_window}"
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]

    def is_system_noise(self, message: str) -> bool:
        """Lọc nhãn trạng thái của Instagram Direct ('Seen', 'Đã xem', 'Active...', 'Typing...')."""
        cleaned = " ".join((message or "").split()).strip()
        if not cleaned:
            return True
        return any(pattern.match(cleaned) for pattern in SYSTEM_NOISE_PATTERNS)

    def is_bot_message(self, message: str) -> bool:
        """Kiểm tra tin nhắn có phải phản hồi chính bot vừa gửi (chống echo nhiều tin gần nhất)."""
        if not message:
            return False
        current_time = time.time()
        msg_norm = message.strip()

        with self._state_lock:
            candidates = list(self.sent_messages)
            if self.last_sent_message:
                candidates.append((self.last_sent_message, self.last_sent_time))

        for sent_text, sent_ts in candidates:
            if not sent_text or (current_time - sent_ts) > 120:
                continue
            sent_norm = sent_text.strip()
            if msg_norm == sent_norm:
                return True
            if len(sent_norm) > 20 and msg_norm in sent_norm:
                return True
            if len(msg_norm) > 20 and sent_norm in msg_norm:
                return True

        return False

    def is_duplicate_message(self, message: str) -> bool:
        current_time = time.time()
        msg_hash = self.create_message_hash(message)

        with self._state_lock:
            if msg_hash in self.processed_set:
                self.duplicate_detections += 1
                return True

            if (
                message == self.last_user_message
                and (current_time - self.last_user_message_time) < 60
            ):
                self.duplicate_detections += 1
                return True

            if (
                self.last_user_message
                and len(message) > 5
                and abs(len(message) - len(self.last_user_message)) <= 2
                and (current_time - self.last_user_message_time) < 30
            ):
                common_chars = sum(
                    1
                    for a, b in zip(message.lower(), self.last_user_message.lower())
                    if a == b
                )
                similarity = common_chars / max(len(message), len(self.last_user_message))
                if similarity > 0.85:
                    self.duplicate_detections += 1
                    return True

        return False

    def mark_message_processed(self, message: str) -> None:
        current_time = time.time()
        msg_hash = self.create_message_hash(message)

        with self._state_lock:
            if len(self.processed_messages) == self.processed_messages.maxlen:
                oldest = self.processed_messages.popleft()
                self.processed_set.discard(oldest)
            self.processed_messages.append(msg_hash)
            self.processed_set.add(msg_hash)

            self.last_user_message = message
            self.last_user_message_time = current_time
            self.total_messages_processed += 1

    def _fetch_latest_message_text(self) -> Optional[str]:
        if not self.driver:
            return None
        for xpath in MESSAGE_TEXT_XPATHS:
            try:
                elements = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_all_elements_located((By.XPATH, xpath))
                )
                if elements:
                    text = (elements[-1].text or "").strip()
                    if text:
                        return text
            except Exception:
                continue
        return None

    def init_first_message(self) -> None:
        if not self.driver:
            self.message_inited = True
            return

        HumanBehavior.jittered_sleep(1.5, 0.2, self.stop_event)
        initial_message = self._fetch_latest_message_text() or ""

        with self._state_lock:
            self.hist_message_input = initial_message
            self.current_message_input = initial_message
            if initial_message:
                self.mark_message_processed(initial_message)
            self.message_inited = True

    def listener(self) -> None:
        self.init_first_message()
        notify_info("Bắt đầu lắng nghe tin nhắn Instagram Direct...", "listener")
        poll_cycle = 0

        while not self.stop_event.is_set():
            try:
                poll_cycle += 1
                # Kiểm tra định kỳ trạng thái checkpoint / rate-limit trên trang
                if self.driver_manager and poll_cycle % 20 == 0:
                    state, reason = self.driver_manager.check_safety()
                    if state != SafetyState.OK:
                        self.safety_halt_reason = reason or state.value
                        notify_critical(f"Tạm dừng bot vì an toàn tài khoản: {self.safety_halt_reason}", "safety")
                        if self.session_manager:
                            cooldown_mins = int(
                                self.config_manager.get("stealth", "safety_cooldown_minutes", 30) or 30
                            )
                            self.session_manager.set_account_cooldown(
                                self.session_name, cooldown_mins, self.safety_halt_reason
                            )
                        self.stop_event.set()
                        break

                latest_message = self._fetch_latest_message_text()
                if latest_message and not self.is_system_noise(latest_message):
                    with self._state_lock:
                        is_changed = latest_message != self.hist_message_input
                    if is_changed:
                        if self.is_bot_message(latest_message) or self.is_duplicate_message(latest_message):
                            with self._state_lock:
                                self.hist_message_input = latest_message
                        else:
                            with self._state_lock:
                                self.current_message_input = latest_message
                                self.hist_message_input = latest_message

                HumanBehavior.jittered_sleep(1.6, 0.3, self.stop_event)

            except Exception as exc:
                self.error_handler.log_error(exc, "listener_loop", ErrorSeverity.MEDIUM)
                HumanBehavior.jittered_sleep(4.0, 0.25, self.stop_event)

    def listen_new_message(self) -> Optional[str]:
        with self._state_lock:
            if not self.message_inited or not self.current_message_input.strip():
                return None
            candidate = self.current_message_input.strip()
            if candidate == self.last_user_message:
                return None

        if self.is_system_noise(candidate) or self.is_bot_message(candidate) or self.is_duplicate_message(candidate):
            return None

        self.mark_message_processed(candidate)
        return candidate


class Sender(Listener):
    """Gửi tin nhắn văn bản và ảnh qua giao diện Instagram Direct tuân thủ safety budget."""

    def _find_composer(self) -> Any:
        if not self.driver:
            return None
        for xpath in COMPOSER_INPUT_XPATHS:
            try:
                return WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
            except Exception:
                continue
        return None

    def send_message(self, text: Optional[str] = None, use_human_typing: Optional[bool] = None) -> bool:
        if not text or not text.strip():
            return False

        clean_text = " ".join(text.replace("\n", " ").split())
        account_key = self.username or "default"
        allowed, budget_reason = self.security_manager.check_outbound_budget(account_key)
        if not allowed:
            notify_warning(f"Tạm hoãn gửi tin nhắn theo safety budget: {budget_reason}", "safety")
            return False

        if not self.driver:
            return False

        composer = self._find_composer()
        if not composer:
            notify_error("Không tìm thấy ô nhập tin nhắn Instagram Direct", "sender")
            return False

        stealth_cfg = self.config_manager.get("stealth") or {}
        if use_human_typing is None:
            use_human_typing = bool(stealth_cfg.get("human_typing", True))

        try:
            composer.click()
            if use_human_typing:
                HumanBehavior.human_type(
                    self.driver,
                    composer,
                    clean_text,
                    min_delay_ms=int(stealth_cfg.get("min_typing_delay_ms", 40)),
                    max_delay_ms=int(stealth_cfg.get("max_typing_delay_ms", 120)),
                    stop_event=self.stop_event,
                )
            else:
                composer.send_keys(clean_text)

            composer.send_keys(Keys.ENTER)
            now = time.time()
            with self._state_lock:
                self.sent_messages.append((clean_text, now))
                self.last_sent_message = clean_text
                self.last_sent_time = now
            self.security_manager.record_outbound_action(account_key, now=now)
            return True
        except Exception as exc:
            self.error_handler.log_error(exc, "send_message", ErrorSeverity.HIGH)
            return False

    def send_image(
        self, file_path: Optional[str] = None, url: Optional[str] = None, caption: str = ""
    ) -> bool:
        """Upload file ảnh trực tiếp vào Instagram Direct hoặc fallback sang gửi link."""
        if file_path and os.path.exists(file_path) and self.driver:
            for xpath in FILE_UPLOAD_INPUT_XPATHS:
                try:
                    file_input = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    file_input.send_keys(os.path.abspath(file_path))
                    HumanBehavior.jittered_sleep(2.5, 0.3, self.stop_event)
                    if caption:
                        self.send_message(caption)
                    else:
                        composer = self._find_composer()
                        if composer:
                            composer.send_keys(Keys.ENTER)
                    return True
                except Exception:
                    continue

        fallback_msg = f"{caption} {url}".strip() if url else caption
        if fallback_msg:
            return self.send_message(fallback_msg)
        return False


class InstaChat(Sender):
    """Bot chính điều phối lắng nghe, AI Gemini, tạo ảnh và theo dõi hiệu suất."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        target_username: Optional[str] = None,
        user_temp_dir_path: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        skip_browser: bool = False,
        start_thread: bool = True,
        ai_bot: Any = None,
    ):
        super().__init__(
            username=username,
            password=password,
            target_username=target_username,
            user_temp_dir_path=user_temp_dir_path,
            skip_browser=skip_browser,
            start_thread=start_thread,
        )

        self.performance_monitor = get_performance_monitor()
        self.analytics_engine = get_analytics_engine()
        self.conversation_insights = get_conversation_insights(self.analytics_engine)
        self.pending_image_request: Optional[Dict[str, Any]] = None
        self.pause_event = threading.Event()

        if ai_bot is not None:
            self.ai_bot = ai_bot
        else:
            try:
                self.ai_bot = create_insta_bot(gemini_api_key)
                notify_info("AI Bot với SQLite Memory System đã sẵn sàng!", "ai_bot")
            except Exception as exc:
                self.error_handler.log_error(exc, "ai_bot_init", ErrorSeverity.CRITICAL)
                notify_critical(f"Không thể khởi tạo AI Bot: {exc}", "ai_bot")
                self.ai_bot = None

    def get_ai_response(self, message: str, sender_name: Optional[str] = None) -> str:
        user_key = sender_name or self.target_username or "user"
        if not self.ai_bot:
            return "ai chưa sẵn sàng, bạn thử lại sau nhé"

        try:
            if self.ai_bot.image_generator and self.ai_bot.image_generator.is_image_request(message):
                initial_response = self.ai_bot.generate_response(message, user_key)
                description = self.ai_bot.image_generator.extract_description(message)
                self.pending_image_request = {
                    "description": description,
                    "username": user_key,
                    "timestamp": time.time(),
                }
                return initial_response
            return self.ai_bot.generate_response(message, user_key)
        except Exception as exc:
            self.error_handler.log_error(exc, "get_ai_response", ErrorSeverity.HIGH, message)
            return "uh mạng hơi chập chờn tí, bạn nhắn lại giúp mình nha"

    def check_and_send_pending_image(self) -> None:
        if not self.pending_image_request or not self.ai_bot:
            return
        if self.ai_bot.is_generating_image and (
            time.time() - self.pending_image_request.get("timestamp", 0) < 1
        ):
            return

        req = self.pending_image_request
        self.pending_image_request = None

        try:
            result = self.ai_bot.process_image_generation(req["description"], req["username"])
            if result.get("success"):
                self.send_image(
                    file_path=result.get("file_path"),
                    url=result.get("url"),
                    caption=result.get("response_text", ""),
                )
            else:
                self.send_message(result.get("response_text", "sorry tạo ảnh bị lỗi rồi :("))
        except Exception as exc:
            self.error_handler.log_error(exc, "pending_image", ErrorSeverity.HIGH)
            self.send_message("sorry tạo ảnh bị lỗi rồi :(")

    def cleanup(self) -> None:
        try:
            notify_info("Đang dừng bot và dọn dẹp tài nguyên...", "cleanup")
            self.stop_event.set()
            if self.listener_thread and self.listener_thread.is_alive():
                self.listener_thread.join(timeout=3.0)

            last_user_preview = self.last_user_message[:30] if self.last_user_message else "None"
            last_bot_preview = self.last_sent_message[:30] if self.last_sent_message else "None"
            notify_info(
                f"Stats: processed={self.total_messages_processed}, "
                f"duplicates={self.duplicate_detections}, "
                f"last_user='{last_user_preview}', last_bot='{last_bot_preview}'",
                "cleanup",
            )

            if self.ai_bot:
                cleanup_insta_bot(self.ai_bot)

            if self.driver_manager:
                self.driver_manager.quit()
            elif self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        except Exception as exc:
            self.error_handler.log_error(exc, "cleanup", ErrorSeverity.MEDIUM)


def _resolve_targets(app_config: Dict[str, Any], override_target: Optional[str] = None) -> List[str]:
    if override_target:
        return [t.strip().lstrip("@") for t in override_target.split(",") if t.strip()]

    targets = app_config.get("target_usernames") or []
    if isinstance(targets, str):
        targets = [t.strip().lstrip("@") for t in targets.split(",") if t.strip()]
    if targets:
        return [str(t).strip().lstrip("@") for t in targets if str(t).strip()]

    single = (app_config.get("target_username") or "").strip().lstrip("@")
    return [single] if single else []


def run_app(
    config_overrides: Optional[Dict[str, Any]] = None,
    start_dashboard: bool = False,
) -> int:
    """Điểm chạy chính của ứng dụng Instagram automation với kiểm tra an toàn và dashboard."""
    config_manager = get_config_manager()
    overrides = config_overrides or {}

    if "headless" in overrides and overrides["headless"] is not None:
        config_manager.set("app", "chrome_options.headless", bool(overrides["headless"]), save=False)
    if overrides.get("proxy_url"):
        config_manager.set("proxy", "url", overrides["proxy_url"], save=False)

    app_config = config_manager.get("app") or {}
    ai_config = config_manager.get("ai") or {}

    gemini_api_key = overrides.get("gemini_api_key") or ai_config.get("api_key") or os.getenv("GEMINI_API_KEY")
    username = overrides.get("username") or app_config.get("instagram_username")
    password = overrides.get("password") or app_config.get("instagram_password")
    targets = _resolve_targets(app_config, overrides.get("target"))

    if not gemini_api_key:
        notify_error("Thiếu GEMINI_API_KEY trong .env hoặc config", "main")
        return 1
    if not username or not password or not targets:
        notify_error(
            "Thiếu INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD hoặc TARGET_USERNAME", "main"
        )
        return 1

    dashboard_server = None
    dash_cfg = config_manager.get("dashboard") or {}
    if start_dashboard or dash_cfg.get("enabled", False):
        from dashboard.server import DashboardServer

        host = overrides.get("dashboard_host") or dash_cfg.get("host", "127.0.0.1")
        port = int(overrides.get("dashboard_port") or dash_cfg.get("port", 8765))
        dashboard_server = DashboardServer(host=host, port=port)
        dashboard_server.start()
        notify_info(f"Dashboard đang chạy tại {dashboard_server.base_url}", "dashboard")

    instagram: Optional[InstaChat] = None
    shutdown_event = threading.Event()

    def _handle_signal(signum, _frame):
        notify_info(f"Nhận tín hiệu dừng ({signum}), đang tắt bot an toàn...", "signal")
        shutdown_event.set()
        if instagram:
            instagram.stop_event.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _handle_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handle_signal)

    try:
        instagram = InstaChat(
            username=username,
            password=password,
            target_username=targets[0],
            gemini_api_key=gemini_api_key,
        )
        if dashboard_server:
            dashboard_server.attach_bot(instagram.ai_bot)
            dashboard_server.attach_controller(instagram)
            dashboard_server.set_runtime_state(
                running=True,
                mode="instagram",
                active_account=username,
                targets=targets,
                proxy=(
                    instagram.driver_manager.active_proxy.safe_url
                    if instagram.driver_manager and instagram.driver_manager.active_proxy
                    else "direct"
                ),
            )

        consecutive_empty = 0
        target_index = 0
        recovery_attempts = 0
        max_recoveries = 3
        stealth_cfg = config_manager.get("stealth") or {}

        while not shutdown_event.is_set() and not instagram.stop_event.is_set():
            # Tạm dừng khi người dùng bấm Pause từ Dashboard
            if instagram.pause_event.is_set():
                HumanBehavior.jittered_sleep(1.0, 0.2, shutdown_event)
                continue

            # Kiểm tra khung giờ hoạt động
            if not HumanBehavior.is_within_active_hours(
                stealth_cfg.get("active_hours_start"), stealth_cfg.get("active_hours_end")
            ):
                HumanBehavior.jittered_sleep(30.0, 0.2, shutdown_event)
                continue

            try:
                new_message = instagram.listen_new_message()
                if new_message is not None:
                    consecutive_empty = 0
                    notify_info(
                        f"Tin nhắn mới từ @{instagram.target_username}: '{new_message[:50]}'", "main"
                    )
                    if stealth_cfg.get("reading_delay_enabled", True):
                        delay = HumanBehavior.calculate_reading_delay(new_message)
                        if not HumanBehavior.jittered_sleep(delay, 0.2, shutdown_event):
                            break

                    ai_response = instagram.get_ai_response(new_message, instagram.target_username)
                    instagram.send_message(ai_response)

                    if instagram.pending_image_request:
                        HumanBehavior.jittered_sleep(1.5, 0.2, shutdown_event)
                        instagram.check_and_send_pending_image()
                else:
                    consecutive_empty += 1
                    if instagram.pending_image_request:
                        instagram.check_and_send_pending_image()

                    # Nếu có nhiều target và đang rảnh, luân chuyển kiểm tra hộp thư mục tiêu tiếp theo
                    if len(targets) > 1 and consecutive_empty >= int(
                        app_config.get("idle_threshold", 20) or 20
                    ):
                        consecutive_empty = 0
                        target_index = (target_index + 1) % len(targets)
                        instagram.go_to_chat(targets[target_index])

                    wait_base = (
                        4.5
                        if consecutive_empty > int(app_config.get("idle_threshold", 20) or 20)
                        else 2.5
                    )
                    HumanBehavior.jittered_sleep(wait_base, 0.25, shutdown_event)

                recovery_attempts = 0
            except WebDriverException as wd_exc:
                recovery_attempts += 1
                get_error_handler().log_error(wd_exc, "webdriver_recovery", ErrorSeverity.HIGH)
                if recovery_attempts > max_recoveries or not instagram.driver_manager:
                    raise
                notify_warning(
                    f"WebDriver bị ngắt kết nối, thử khôi phục ({recovery_attempts}/{max_recoveries})...",
                    "driver_recovery",
                )
                instagram.driver = instagram.driver_manager.recover_driver(rotate_proxy=True)
                instagram.go_to_chat(targets[target_index])

        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        get_error_handler().log_error(exc, "run_app", ErrorSeverity.CRITICAL)
        notify_critical(f"Lỗi nghiêm trọng trong app: {exc}", "main")
        return 1
    finally:
        if instagram:
            instagram.cleanup()
        if dashboard_server:
            dashboard_server.stop()


if __name__ == "__main__":
    raise SystemExit(run_app())
