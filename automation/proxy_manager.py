from dataclasses import dataclass
import json
import os
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests


@dataclass(frozen=True)
class ProxyConfig:
    """Biểu diễn cấu hình một proxy hỗ trợ ẩn thông tin nhạy cảm khi ghi log."""

    scheme: str = "http"
    host: str = ""
    port: int = 8080
    username: Optional[str] = None
    password: Optional[str] = None
    label: str = ""

    @property
    def requires_auth(self) -> bool:
        return bool(self.username) and self.password is not None

    @property
    def raw_url(self) -> str:
        auth = ""
        if self.username is not None and self.password is not None:
            auth = f"{self.username}:{self.password}@"
        elif self.username is not None:
            auth = f"{self.username}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def safe_url(self) -> str:
        """URL đã che mật khẩu để dùng an toàn trong log và giao diện Dashboard."""
        if self.username:
            return f"{self.scheme}://{self.username}:***@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def chrome_arg(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def requests_proxies(self) -> Dict[str, str]:
        return {"http": self.raw_url, "https": self.raw_url}


def parse_proxy_url(proxy_str: str) -> ProxyConfig:
    """Phân tích chuỗi proxy theo chuẩn URL hoặc host:port[:user:pass]."""
    raw = (proxy_str or "").strip()
    if not raw:
        raise ValueError("Chuỗi proxy không được rỗng")

    if "://" not in raw:
        parts = raw.split(":")
        if len(parts) == 2:
            host, port_str = parts
            user, pwd = None, None
        elif len(parts) == 4:
            host, port_str, user, pwd = parts
        else:
            raise ValueError(f"Định dạng proxy không hợp lệ: {raw}")

        port = int(port_str)
        if not host or not (1 <= port <= 65535):
            raise ValueError(f"Port proxy không hợp lệ: {port_str}")
        return ProxyConfig(scheme="http", host=host, port=port, username=user, password=pwd)

    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Thiếu host hoặc port trong proxy URL: {raw}")

    scheme = (parsed.scheme or "http").lower()
    if scheme not in {"http", "https", "socks5", "socks4"}:
        raise ValueError(f"Giao thức proxy không hỗ trợ: {scheme}")

    return ProxyConfig(
        scheme=scheme,
        host=parsed.hostname,
        port=int(parsed.port),
        username=parsed.username,
        password=parsed.password,
    )


def create_chrome_proxy_auth_extension(proxy: ProxyConfig, target_dir: str) -> str:
    """Tạo extension Chrome Manifest V3 tự động xác thực proxy có username/password.

    Chrome không cho truyền user:pass trực tiếp qua cờ --proxy-server, nên extension
    này đăng ký chrome.proxy.settings và lắng nghe onAuthRequired để trả credentials.
    """
    os.makedirs(target_dir, exist_ok=True)
    manifest = {
        "manifest_version": 3,
        "name": "InstaChat Proxy Auth",
        "version": "1.0.0",
        "permissions": ["proxy", "webRequest", "webRequestAuthProvider"],
        "host_permissions": ["<all_urls>"],
        "background": {"service_worker": "background.js"},
    }

    scheme_json = json.dumps(proxy.scheme)
    host_json = json.dumps(proxy.host)
    user_json = json.dumps(proxy.username or "")
    pass_json = json.dumps(proxy.password or "")

    background_js = f"""
const config = {{
  mode: "fixed_servers",
  rules: {{
    singleProxy: {{
      scheme: {scheme_json},
      host: {host_json},
      port: {int(proxy.port)}
    }},
    bypassList: ["localhost", "127.0.0.1"]
  }}
}};

chrome.proxy.settings.set({{ value: config, scope: "regular" }}, () => {{}});

chrome.webRequest.onAuthRequired.addListener(
  () => ({{
    authCredentials: {{
      username: {user_json},
      password: {pass_json}
    }}
  }}),
  {{ urls: ["<all_urls>"] }},
  ["blocking"]
);
""".lstrip()

    with open(os.path.join(target_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(target_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)

    return target_dir


class ProxyPool:
    """Quản lý danh sách proxy có gắn cứng (sticky) theo tài khoản và tự chuyển dự phòng khi lỗi."""

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        proxy_list: Optional[str] = None,
        sticky_per_account: bool = True,
    ):
        self.sticky_per_account = sticky_per_account
        self._lock = threading.RLock()
        self.proxies: List[ProxyConfig] = []
        self.account_bindings: Dict[str, int] = {}
        self.failed_proxies: Set[str] = set()
        self._rr_index = 0

        self._load_sources(proxy_url=proxy_url, proxy_list=proxy_list)

    def _load_sources(self, proxy_url: Optional[str], proxy_list: Optional[str]) -> None:
        raw_entries: List[str] = []
        if proxy_url:
            raw_entries.append(proxy_url)

        if proxy_list:
            if os.path.isfile(proxy_list):
                with open(proxy_list, "r", encoding="utf-8") as f:
                    for line in f:
                        cleaned = line.strip()
                        if cleaned and not cleaned.startswith("#"):
                            raw_entries.append(cleaned)
            else:
                for token in proxy_list.replace(";", "\n").replace(",", "\n").splitlines():
                    cleaned = token.strip()
                    if cleaned and not cleaned.startswith("#"):
                        raw_entries.append(cleaned)

        seen_raw: Set[str] = set()
        for entry in raw_entries:
            try:
                parsed = parse_proxy_url(entry)
                if parsed.raw_url not in seen_raw:
                    seen_raw.add(parsed.raw_url)
                    self.proxies.append(parsed)
            except ValueError as exc:
                print(f"[PROXY] ⚠️ Bỏ qua proxy không hợp lệ ({exc})")

    @property
    def is_empty(self) -> bool:
        return len(self.proxies) == 0

    def bind_explicit_proxy(self, account_id: str, proxy_url: str) -> Optional[ProxyConfig]:
        """Khôi phục proxy đã gán trước đó cho account_id nếu còn nằm trong pool hoặc hợp lệ."""
        try:
            target = parse_proxy_url(proxy_url)
        except ValueError:
            return None

        with self._lock:
            for idx, item in enumerate(self.proxies):
                if item.safe_url == target.safe_url or item.raw_url == target.raw_url:
                    self.account_bindings[account_id] = idx
                    return item
        return None

    def get_proxy_for_account(self, account_id: str = "default") -> Optional[ProxyConfig]:
        with self._lock:
            if not self.proxies:
                return None

            if self.sticky_per_account and account_id in self.account_bindings:
                idx = self.account_bindings[account_id]
                candidate = self.proxies[idx]
                if candidate.raw_url not in self.failed_proxies:
                    return candidate

            for offset in range(len(self.proxies)):
                idx = (self._rr_index + offset) % len(self.proxies)
                candidate = self.proxies[idx]
                if candidate.raw_url not in self.failed_proxies:
                    self._rr_index = (idx + 1) % len(self.proxies)
                    if self.sticky_per_account:
                        self.account_bindings[account_id] = idx
                    return candidate

            # Nếu toàn bộ đều từng lỗi, reset danh sách lỗi để thử lại từ đầu
            self.failed_proxies.clear()
            idx = self._rr_index % len(self.proxies)
            self._rr_index = (idx + 1) % len(self.proxies)
            if self.sticky_per_account:
                self.account_bindings[account_id] = idx
            return self.proxies[idx]

    def rotate_proxy(self, account_id: str = "default") -> Optional[ProxyConfig]:
        """Đánh dấu proxy hiện tại của account là lỗi và chuyển sang proxy khỏe tiếp theo."""
        with self._lock:
            if not self.proxies:
                return None

            if account_id in self.account_bindings:
                current_idx = self.account_bindings[account_id]
                self.failed_proxies.add(self.proxies[current_idx].raw_url)
                start = (current_idx + 1) % len(self.proxies)
            else:
                start = self._rr_index % len(self.proxies)

            for offset in range(len(self.proxies)):
                idx = (start + offset) % len(self.proxies)
                candidate = self.proxies[idx]
                if candidate.raw_url not in self.failed_proxies:
                    self.account_bindings[account_id] = idx
                    self._rr_index = (idx + 1) % len(self.proxies)
                    return candidate

            return None

    def get_healthy_proxy(
        self,
        account_id: str = "default",
        check_health: bool = False,
        timeout: float = 8.0,
    ) -> Optional[ProxyConfig]:
        """Lấy proxy cho tài khoản; nếu check_health=True sẽ tự thử xoay sang proxy sống khác khi lỗi."""
        candidate = self.get_proxy_for_account(account_id)
        if candidate is None or not check_health:
            return candidate

        total = len(self.proxies)
        for attempt in range(total):
            if candidate is None:
                return None
            ok, _ = self.check_health(candidate, timeout=timeout)
            if ok:
                return candidate
            if attempt < total - 1:
                candidate = self.rotate_proxy(account_id)
        return None

    def mark_failed(self, proxy: ProxyConfig) -> None:
        with self._lock:
            self.failed_proxies.add(proxy.raw_url)

    def mark_healthy(self, proxy: ProxyConfig) -> None:
        with self._lock:
            self.failed_proxies.discard(proxy.raw_url)

    def check_health(
        self, proxy: ProxyConfig, timeout: float = 8.0, check_url: str = "https://api.ipify.org?format=json"
    ) -> Tuple[bool, str]:
        try:
            resp = requests.get(check_url, proxies=proxy.requests_proxies, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            ip = data.get("ip", "unknown")
            self.mark_healthy(proxy)
            return True, str(ip)
        except Exception as exc:
            self.mark_failed(proxy)
            return False, str(exc)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_proxies": len(self.proxies),
                "failed_count": len(self.failed_proxies),
                "sticky_per_account": self.sticky_per_account,
                "proxies": [
                    {
                        "url": p.safe_url,
                        "healthy": p.raw_url not in self.failed_proxies,
                    }
                    for p in self.proxies
                ],
                "bindings": {
                    acct: self.proxies[idx].safe_url
                    for acct, idx in self.account_bindings.items()
                    if 0 <= idx < len(self.proxies)
                },
            }
