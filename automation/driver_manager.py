from enum import Enum
import os
import shutil
import tempfile
from typing import Any, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from automation.proxy_manager import ProxyConfig, ProxyPool, create_chrome_proxy_auth_extension
from automation.selectors import (
    COOKIE_CONSENT_XPATHS,
    DISMISS_POPUP_XPATHS,
    LOGIN_PASSWORD_SELECTORS,
    LOGIN_SUCCESS_INDICATORS,
    LOGIN_USERNAME_SELECTORS,
    SAFETY_TEXT_RULES,
    SAFETY_URL_RULES,
)
from automation.stealth import (
    BrowserFingerprint,
    HumanBehavior,
    apply_cdp_stealth,
    build_chrome_options,
)
from config.config_manager import ConfigManager, get_config_manager, get_data_dir
from memory.nlp import sanitize_filename
from monitoring.error_handler import (
    InstagramAuthError,
    InstagramCheckpointError,
    InstagramRateLimitError,
)
from security.session_manager import SessionManager, get_session_manager


class SafetyState(Enum):
    OK = "ok"
    RATE_LIMITED = "rate_limited"
    CHALLENGE = "challenge"
    TWO_FACTOR = "two_factor"
    SUSPENDED = "suspended"
    LOGGED_OUT = "logged_out"


class AccountSafetyDetector:
    """Phát hiện sớm trạng thái bất thường của tài khoản Instagram (checkpoint, rate-limit, 2FA)."""

    @staticmethod
    def inspect(current_url: str, page_text: str) -> Tuple[SafetyState, str]:
        url_lower = (current_url or "").lower()
        text_lower = (page_text or "").lower()

        for pattern in SAFETY_URL_RULES["suspended"]:
            if pattern in url_lower:
                return SafetyState.SUSPENDED, f"Phát hiện URL đình chỉ tài khoản: {current_url}"

        for pattern in SAFETY_URL_RULES["challenge"]:
            if pattern in url_lower:
                return SafetyState.CHALLENGE, f"Instagram yêu cầu checkpoint/xác minh: {current_url}"

        for pattern in SAFETY_URL_RULES["two_factor"]:
            if pattern in url_lower:
                return SafetyState.TWO_FACTOR, "Instagram yêu cầu xác thực 2 bước (2FA)"

        for pattern in SAFETY_TEXT_RULES["suspended"]:
            if pattern in text_lower:
                return SafetyState.SUSPENDED, f"Phát hiện thông báo khóa tài khoản: '{pattern}'"

        for pattern in SAFETY_TEXT_RULES["challenge"]:
            if pattern in text_lower:
                return SafetyState.CHALLENGE, f"Phát hiện cảnh báo hành vi tự động/checkpoint: '{pattern}'"

        for pattern in SAFETY_TEXT_RULES["rate_limited"]:
            if pattern in text_lower:
                return SafetyState.RATE_LIMITED, f"Instagram giới hạn tốc độ (rate-limit): '{pattern}'"

        for pattern in SAFETY_URL_RULES["logged_out"]:
            if pattern in url_lower:
                return SafetyState.LOGGED_OUT, "Phiên đăng nhập đã hết hạn, bị chuyển về trang login"

        return SafetyState.OK, ""


class InstagramDriverManager:
    """Điều phối ChromeDriver với persistent profile, encrypted cookies, stealth CDP và proxy sticky."""

    def __init__(
        self,
        username: str,
        password: str,
        target_username: str,
        session_name: Optional[str] = None,
        config_manager: Optional[ConfigManager] = None,
        session_manager: Optional[SessionManager] = None,
        proxy_pool: Optional[ProxyPool] = None,
    ):
        self.username = username
        self.password = password
        self.target_username = target_username
        self.config_manager = config_manager or get_config_manager()
        self.session_manager = session_manager or get_session_manager()
        self.session_name = session_name or f"session_{username}_{target_username}"

        proxy_cfg = self.config_manager.get("proxy") or {}
        self.proxy_pool = proxy_pool or ProxyPool(
            proxy_url=proxy_cfg.get("url"),
            proxy_list=proxy_cfg.get("list"),
            sticky_per_account=bool(proxy_cfg.get("sticky_per_account", True)),
        )

        self.driver: Optional[webdriver.Chrome] = None
        self.active_proxy: Optional[ProxyConfig] = None
        self.fingerprint: BrowserFingerprint = self._load_or_create_fingerprint()
        self.profile_dir: Optional[str] = None
        self.is_ephemeral_profile = False
        self.proxy_ext_dir: Optional[str] = None

        self._ensure_session_record()

    def _ensure_session_record(self) -> None:
        if not self.session_manager.get_session(self.session_name):
            self.session_manager.create_session(
                self.username, self.password, self.target_username, self.session_name
            )

    def _load_or_create_fingerprint(self) -> BrowserFingerprint:
        stealth_cfg = self.config_manager.get("stealth") or {}
        locale = stealth_cfg.get("locale", "vi-VN")
        timezone = stealth_cfg.get("timezone", "Asia/Ho_Chi_Minh")
        fp_dict = self.session_manager.get_or_init_fingerprint(
            self.session_name,
            lambda: BrowserFingerprint.generate_random(locale=locale, timezone=timezone).to_dict(),
        )
        return BrowserFingerprint.from_dict(fp_dict)

    def _select_proxy(self) -> Optional[ProxyConfig]:
        if self.proxy_pool.is_empty:
            return None

        saved_proxy = self.session_manager.get_assigned_proxy(self.session_name)
        if saved_proxy:
            bound = self.proxy_pool.bind_explicit_proxy(self.username, saved_proxy)
            if bound is not None:
                return bound

        chosen = self.proxy_pool.get_proxy_for_account(self.username)
        if chosen is not None:
            self.session_manager.set_assigned_proxy(self.session_name, chosen.safe_url)
        return chosen

    def init_driver(self) -> webdriver.Chrome:
        """Khởi tạo ChromeDriver kèm profile bền vững, proxy (nếu có) và stealth CDP."""
        app_cfg = self.config_manager.get("app") or {}
        chrome_cfg = app_cfg.get("chrome_options", {})
        stealth_cfg = self.config_manager.get("stealth") or {}

        persistent = bool(stealth_cfg.get("persistent_profile", True))
        if persistent:
            safe_user = sanitize_filename(self.username, default_name="default_user")
            self.profile_dir = os.path.join(get_data_dir("profiles"), safe_user)
            os.makedirs(self.profile_dir, exist_ok=True)
            self.is_ephemeral_profile = False
        else:
            self.profile_dir = tempfile.mkdtemp(prefix="instachat_chrome_")
            self.is_ephemeral_profile = True

        self.active_proxy = self._select_proxy()
        proxy_arg = None
        proxy_ext_dir = None

        if self.active_proxy is not None:
            if self.active_proxy.requires_auth:
                self.proxy_ext_dir = tempfile.mkdtemp(prefix="instachat_proxy_ext_")
                proxy_ext_dir = create_chrome_proxy_auth_extension(
                    self.active_proxy, self.proxy_ext_dir
                )
            else:
                proxy_arg = self.active_proxy.chrome_arg

        options = build_chrome_options(
            fingerprint=self.fingerprint,
            profile_dir=self.profile_dir,
            headless=bool(chrome_cfg.get("headless", True)),
            proxy_arg=proxy_arg,
            proxy_ext_dir=proxy_ext_dir,
            user_agent=stealth_cfg.get("user_agent") or "",
            no_sandbox=bool(chrome_cfg.get("no_sandbox", True)),
            disable_dev_shm_usage=bool(chrome_cfg.get("disable_dev_shm_usage", True)),
        )

        # Selenium 4 tự quản lý ChromeDriver qua Selenium Manager (không cần webdriver-manager).
        self.driver = webdriver.Chrome(options=options)
        apply_cdp_stealth(self.driver, self.fingerprint)

        self.session_manager.update_session(
            self.session_name,
            {"chrome_profile_path": self.profile_dir, "status": "driver_ready"},
        )
        return self.driver

    def _dismiss_cookie_banner(self) -> None:
        if not self.driver:
            return
        for xpath in COOKIE_CONSENT_XPATHS:
            try:
                btn = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                btn.click()
                return
            except Exception:
                continue

    def _dismiss_post_login_popups(self) -> None:
        if not self.driver:
            return
        for xpath in DISMISS_POPUP_XPATHS:
            try:
                btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                btn.click()
                HumanBehavior.jittered_sleep(0.8, 0.3)
            except Exception:
                continue

    def _is_logged_in(self, timeout_per_indicator: float = 2.0) -> bool:
        if not self.driver:
            return False
        for xpath in LOGIN_SUCCESS_INDICATORS:
            try:
                WebDriverWait(self.driver, timeout_per_indicator).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                return True
            except Exception:
                continue
        return False

    def restore_cookies_and_check_login(self) -> bool:
        """Thử khôi phục phiên từ cookie mã hóa để bỏ qua màn hình đăng nhập."""
        if not self.driver:
            return False

        self.driver.get("https://www.instagram.com/")
        HumanBehavior.jittered_sleep(2.0, 0.3)
        self._dismiss_cookie_banner()

        if self._is_logged_in(timeout_per_indicator=1.5):
            self._dismiss_post_login_popups()
            self.session_manager.record_login_attempt(self.session_name, success=True)
            return True

        cookies = self.session_manager.load_chrome_cookies(self.session_name)
        if not cookies:
            return False

        loaded_any = False
        for cookie in cookies:
            clean_cookie = {k: v for k, v in cookie.items() if k != "sameSite" or v in {"Strict", "Lax", "None"}}
            try:
                self.driver.add_cookie(clean_cookie)
                loaded_any = True
            except Exception:
                continue

        if not loaded_any:
            return False

        self.driver.refresh()
        HumanBehavior.jittered_sleep(2.5, 0.3)
        if self._is_logged_in(timeout_per_indicator=2.0):
            self._dismiss_post_login_popups()
            self.session_manager.record_login_attempt(self.session_name, success=True)
            return True
        return False

    def _find_input(self, selectors: tuple, timeout: int = 20) -> Any:
        assert self.driver is not None
        for strategy, locator in selectors:
            by = By.NAME if strategy == "name" else By.CSS_SELECTOR
            try:
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, locator))
                )
            except Exception:
                continue
        return None

    def login(self) -> None:
        """Đăng nhập Instagram: ưu tiên tái sử dụng cookie/profile trước khi nhập mật khẩu."""
        if not self.driver:
            raise RuntimeError("Driver chưa được khởi tạo")

        acct_cfg = self.config_manager.get("security", "account_protection", {}) or {}
        can_login, msg = self.session_manager.can_attempt_login(
            self.session_name,
            max_attempts=int(acct_cfg.get("max_login_attempts", 3)),
            cooldown_minutes=int(acct_cfg.get("cooldown_minutes", 30)),
        )
        if not can_login:
            raise InstagramRateLimitError(f"Login bị chặn bởi cooldown: {msg}")

        if self.restore_cookies_and_check_login():
            print("[DRIVER] ✅ Đã khôi phục phiên Instagram từ profile/cookies, không cần login lại.")
            self.save_current_cookies()
            return

        login_timeout = int(
            self.config_manager.get("app", "instagram.login_timeout", 30) or 30
        )
        self.driver.get("https://www.instagram.com/accounts/login/")
        HumanBehavior.jittered_sleep(2.5, 0.3)
        self._dismiss_cookie_banner()

        username_input = self._find_input(LOGIN_USERNAME_SELECTORS, timeout=login_timeout)
        if not username_input:
            state, reason = self.check_safety()
            self._raise_for_safety_state(state, reason)
            self.session_manager.record_login_attempt(self.session_name, success=False)
            raise InstagramAuthError("Không tìm thấy ô nhập username trên trang đăng nhập Instagram")

        username_input.clear()
        HumanBehavior.human_type(self.driver, username_input, self.username)
        HumanBehavior.jittered_sleep(0.7, 0.3)

        password_input = self._find_input(LOGIN_PASSWORD_SELECTORS, timeout=10)
        if not password_input:
            self.session_manager.record_login_attempt(self.session_name, success=False)
            raise InstagramAuthError("Không tìm thấy ô nhập password trên trang đăng nhập Instagram")

        password_input.clear()
        HumanBehavior.human_type(self.driver, password_input, self.password)
        HumanBehavior.jittered_sleep(0.5, 0.3)
        password_input.send_keys(Keys.ENTER)

        HumanBehavior.jittered_sleep(4.0, 0.3)
        state, reason = self.check_safety()
        if state in {SafetyState.CHALLENGE, SafetyState.SUSPENDED, SafetyState.TWO_FACTOR, SafetyState.RATE_LIMITED}:
            self.session_manager.record_login_attempt(self.session_name, success=False)
            cooldown_mins = int(
                self.config_manager.get("stealth", "safety_cooldown_minutes", 30) or 30
            )
            self.session_manager.set_account_cooldown(self.session_name, cooldown_mins, reason)
            self._raise_for_safety_state(state, reason)

        if self._is_logged_in(timeout_per_indicator=3.0):
            self._dismiss_post_login_popups()
            self.session_manager.record_login_attempt(self.session_name, success=True)
            self.save_current_cookies()
            return

        self.session_manager.record_login_attempt(self.session_name, success=False)
        raise InstagramAuthError(
            f"Không thể xác nhận đăng nhập thành công. URL hiện tại: {self.driver.current_url}"
        )

    def _raise_for_safety_state(self, state: SafetyState, reason: str) -> None:
        if state in {SafetyState.CHALLENGE, SafetyState.SUSPENDED, SafetyState.TWO_FACTOR}:
            raise InstagramCheckpointError(reason)
        if state == SafetyState.RATE_LIMITED:
            raise InstagramRateLimitError(reason)

    def check_safety(self) -> Tuple[SafetyState, str]:
        if not self.driver:
            return SafetyState.OK, ""
        try:
            url = self.driver.current_url
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            url = getattr(self.driver, "current_url", "")
            body_text = getattr(self.driver, "page_source", "") or ""
        return AccountSafetyDetector.inspect(url, body_text)

    def save_current_cookies(self) -> bool:
        if not self.driver:
            return False
        try:
            cookies = self.driver.get_cookies()
            if cookies:
                return self.session_manager.save_chrome_cookies(self.session_name, cookies)
        except Exception:
            pass
        return False

    def quit(self) -> None:
        """Lưu cookies lần cuối và dọn dẹp tài nguyên trình duyệt an toàn."""
        if self.driver is not None:
            try:
                self.save_current_cookies()
            except Exception:
                pass
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        if self.proxy_ext_dir and os.path.exists(self.proxy_ext_dir):
            shutil.rmtree(self.proxy_ext_dir, ignore_errors=True)
            self.proxy_ext_dir = None

        if self.is_ephemeral_profile and self.profile_dir and os.path.exists(self.profile_dir):
            shutil.rmtree(self.profile_dir, ignore_errors=True)
            self.profile_dir = None

    def recover_driver(self, rotate_proxy: bool = False) -> webdriver.Chrome:
        """Khôi phục ChromeDriver khi crash hoặc đứt kết nối giữa chừng (tùy chọn đổi proxy)."""
        if rotate_proxy and not self.proxy_pool.is_empty:
            new_proxy = self.proxy_pool.rotate_proxy(self.username)
            if new_proxy is not None:
                self.session_manager.set_assigned_proxy(self.session_name, new_proxy.safe_url)
        self.quit()
        driver = self.init_driver()
        self.login()
        return driver
