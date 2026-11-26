from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from selenium.webdriver.chrome.options import Options

_VIEWPORT_POOL: List[Tuple[int, int]] = [
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1600, 900),
    (1920, 1080),
]

_WEBGL_POOL: List[Tuple[str, str]] = [
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]


@dataclass
class BrowserFingerprint:
    """Thông số fingerprint đồng bộ giúp mỗi tài khoản giữ danh tính nhất quán giữa các lần chạy."""

    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "vi-VN"
    languages: List[str] = field(default_factory=lambda: ["vi-VN", "vi", "en-US", "en"])
    timezone: str = "Asia/Ho_Chi_Minh"
    platform: str = "Win32"
    hardware_concurrency: int = 8
    device_memory: int = 8
    webgl_vendor: str = _WEBGL_POOL[0][0]
    webgl_renderer: str = _WEBGL_POOL[0][1]

    @classmethod
    def generate_random(
        cls, locale: str = "vi-VN", timezone: str = "Asia/Ho_Chi_Minh"
    ) -> "BrowserFingerprint":
        width, height = random.choice(_VIEWPORT_POOL)
        vendor, renderer = random.choice(_WEBGL_POOL)
        lang_primary = locale.split("-")[0] if "-" in locale else locale
        languages = [locale, lang_primary, "en-US", "en"]
        # Giữ thứ tự đồng thời khử trùng lặp
        dedup_langs = list(dict.fromkeys(languages))
        return cls(
            viewport_width=width,
            viewport_height=height,
            locale=locale,
            languages=dedup_langs,
            timezone=timezone,
            platform="Win32",
            hardware_concurrency=random.choice([4, 8, 12, 16]),
            device_memory=random.choice([4, 8, 16]),
            webgl_vendor=vendor,
            webgl_renderer=renderer,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrowserFingerprint":
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


def build_chrome_options(
    fingerprint: BrowserFingerprint,
    profile_dir: Optional[str] = None,
    headless: bool = True,
    proxy_arg: Optional[str] = None,
    proxy_ext_dir: Optional[str] = None,
    user_agent: Optional[str] = None,
    no_sandbox: bool = True,
    disable_dev_shm_usage: bool = True,
) -> Options:
    """Xây dựng ChromeOptions tránh các dấu hiệu lộ automation phổ biến."""
    chrome_options = Options()

    if headless:
        chrome_options.add_argument("--headless=new")

    if profile_dir:
        chrome_options.add_argument(f"--user-data-dir={profile_dir}")

    if no_sandbox:
        chrome_options.add_argument("--no-sandbox")
    if disable_dev_shm_usage:
        chrome_options.add_argument("--disable-dev-shm-usage")

    chrome_options.add_argument(
        f"--window-size={fingerprint.viewport_width},{fingerprint.viewport_height}"
    )
    chrome_options.add_argument(f"--lang={fingerprint.locale}")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--mute-audio")

    # Chỉ đặt User-Agent khi người dùng cấu hình rõ để tránh lệch với Sec-CH-UA của Chrome thật.
    if user_agent and user_agent.strip():
        chrome_options.add_argument(f"--user-agent={user_agent.strip()}")

    # Chỉ tắt extensions khi không dùng proxy auth extension (nếu tắt sẽ chặn extension xác thực).
    if proxy_ext_dir:
        chrome_options.add_argument(f"--load-extension={proxy_ext_dir}")
    else:
        chrome_options.add_argument("--disable-extensions")
        if proxy_arg:
            chrome_options.add_argument(f"--proxy-server={proxy_arg}")

    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_experimental_option(
        "prefs",
        {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "geolocation": 2,
                "media_stream": 2,
            },
            "intl.accept_languages": ",".join(fingerprint.languages),
        },
    )
    return chrome_options


def build_stealth_init_script(fingerprint: BrowserFingerprint) -> str:
    """Sinh đoạn JavaScript inject qua CDP trước khi trang tải để ẩn thuộc tính WebDriver."""
    langs_json = json.dumps(fingerprint.languages)
    platform_json = json.dumps(fingerprint.platform)
    vendor_json = json.dumps(fingerprint.webgl_vendor)
    renderer_json = json.dumps(fingerprint.webgl_renderer)

    return f"""
(() => {{
  try {{
    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
  }} catch (e) {{}}

  try {{
    Object.defineProperty(navigator, 'languages', {{ get: () => {langs_json} }});
    Object.defineProperty(navigator, 'language', {{ get: () => {langs_json}[0] }});
    Object.defineProperty(navigator, 'platform', {{ get: () => {platform_json} }});
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {int(fingerprint.hardware_concurrency)} }});
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {int(fingerprint.device_memory)} }});
  }} catch (e) {{}}

  if (!window.chrome) {{
    window.chrome = {{ runtime: {{}} }};
  }}

  try {{
    if (navigator.plugins && navigator.plugins.length === 0) {{
      Object.defineProperty(navigator, 'plugins', {{
        get: () => [
          {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' }},
          {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' }},
          {{ name: 'Native Client', filename: 'internal-nacl-plugin' }}
        ]
      }});
    }}
  }} catch (e) {{}}

  try {{
    const origQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (origQuery) {{
      window.navigator.permissions.query = (parameters) => (
        parameters && parameters.name === 'notifications'
          ? Promise.resolve({{ state: Notification.permission }})
          : origQuery(parameters)
      );
    }}
  }} catch (e) {{}}

  try {{
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
      if (parameter === 37445) return {vendor_json};
      if (parameter === 37446) return {renderer_json};
      return getParameter.apply(this, arguments);
    }};
  }} catch (e) {{}}
}})();
""".strip()


def apply_cdp_stealth(driver: Any, fingerprint: BrowserFingerprint) -> None:
    """Áp dụng stealth script và timezone override qua Chrome DevTools Protocol."""
    script = build_stealth_init_script(fingerprint)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
    except Exception as exc:
        print(f"[STEALTH] ⚠️ Không thể gắn CDP stealth script: {exc}")

    try:
        driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": fingerprint.timezone})
    except Exception:
        pass


class HumanBehavior:
    """Mô phỏng nhịp độ đọc, gõ phím và khung giờ hoạt động giống người dùng thật."""

    @staticmethod
    def calculate_reading_delay(
        message: str, base_min: float = 0.7, base_max: float = 1.8
    ) -> float:
        text_len = len((message or "").strip())
        read_time = min(4.5, text_len * 0.025)
        return round(read_time + random.uniform(base_min, base_max), 3)

    @staticmethod
    def jittered_sleep(
        base_seconds: float,
        variance: float = 0.3,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        """Ngủ ngẫu nhiên quanh base_seconds; trả về False nếu stop_event được kích hoạt."""
        low = max(0.05, base_seconds * (1.0 - variance))
        high = max(low, base_seconds * (1.0 + variance))
        duration = random.uniform(low, high)
        if stop_event is not None:
            return not stop_event.wait(timeout=duration)
        time.sleep(duration)
        return True

    @staticmethod
    def human_type(
        driver: Any,
        element: Any,
        text: str,
        min_delay_ms: int = 40,
        max_delay_ms: int = 120,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Gõ từng ký tự có độ trễ tự nhiên và xử lý an toàn emoji (non-BMP) qua JS."""
        sanitized = (text or "").replace("\r", " ").replace("\n", " ")
        min_s = max(0.005, min_delay_ms / 1000.0)
        max_s = max(min_s, max_delay_ms / 1000.0)

        for ch in sanitized:
            if stop_event is not None and stop_event.is_set():
                return

            if ord(ch) > 0xFFFF:
                # ChromeDriver từ chối send_keys với ký tự ngoài BMP (emoji); dùng insertText thay thế.
                driver.execute_script(
                    "document.execCommand('insertText', false, arguments[0]);", ch
                )
            else:
                element.send_keys(ch)

            delay = random.uniform(min_s, max_s)
            if ch in {".", ",", "!", "?", " "}:
                delay += random.uniform(0.02, 0.08)

            if stop_event is not None:
                if stop_event.wait(timeout=delay):
                    return
            else:
                time.sleep(delay)

    @staticmethod
    def is_within_active_hours(
        start_hour: Optional[int],
        end_hour: Optional[int],
        now: Optional[datetime] = None,
    ) -> bool:
        """Kiểm tra giờ hiện tại có nằm trong khung hoạt động cho phép hay không."""
        if start_hour is None or end_hour is None:
            return True

        start = int(start_hour) % 24
        end = int(end_hour) % 24
        current_hour = (now or datetime.now()).hour

        if start == end:
            return True
        if start < end:
            return start <= current_hour < end
        # Khung giờ qua nửa đêm (ví dụ 22h -> 06h)
        return current_hour >= start or current_hour < end
