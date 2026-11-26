import base64
from datetime import datetime, timedelta
import hashlib
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from cryptography.fernet import Fernet

from config.config_manager import get_data_dir


class SessionManager:
    """Quản lý session, fingerprint cố định theo tài khoản và cookies mã hóa bằng Fernet + JSON."""

    def __init__(
        self,
        session_file: Optional[str] = None,
        key_file: Optional[str] = None,
    ):
        sessions_dir = get_data_dir("sessions")
        self.session_file = session_file or os.path.join(sessions_dir, "sessions.json")
        self.key_file = key_file or os.path.join(sessions_dir, "session.key")
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.current_session: Optional[str] = None
        self._lock = threading.RLock()

        os.makedirs(os.path.dirname(self.session_file) or sessions_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.key_file) or sessions_dir, exist_ok=True)

        self.cipher = self._init_encryption()
        self.load_sessions()

    def _init_encryption(self) -> Optional[Fernet]:
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, "rb") as f:
                    key = f.read().strip()
            else:
                key = Fernet.generate_key()
                with open(self.key_file, "wb") as f:
                    f.write(key)
            return Fernet(key)
        except Exception as exc:
            print(f"[SESSION] ⚠️ Lỗi khởi tạo encryption: {exc}")
            return None

    def encrypt_data(self, data: Any) -> str:
        if isinstance(data, bytes):
            raw = data
        elif isinstance(data, str):
            raw = data.encode("utf-8")
        else:
            raw = str(data).encode("utf-8")

        if not self.cipher:
            return raw.decode("utf-8", errors="replace")

        try:
            return self.cipher.encrypt(raw).decode("utf-8")
        except Exception as exc:
            print(f"[SESSION] ⚠️ Lỗi mã hóa: {exc}")
            return raw.decode("utf-8", errors="replace")

    def decrypt_data(self, encrypted_data: Any) -> Optional[str]:
        if encrypted_data is None:
            return None
        if not self.cipher:
            return str(encrypted_data)
        try:
            token = (
                encrypted_data.encode("utf-8")
                if isinstance(encrypted_data, str)
                else encrypted_data
            )
            return self.cipher.decrypt(token).decode("utf-8")
        except Exception as exc:
            print(f"[SESSION] ⚠️ Lỗi giải mã: {exc}")
            return None

    def create_session(
        self,
        username: str,
        password: str,
        target_username: str,
        session_name: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        with self._lock:
            if not session_name:
                session_name = f"session_{username}_{int(time.time())}"

            encrypted_password = self.encrypt_data(password)
            now = datetime.now().isoformat()
            session_data: Dict[str, Any] = {
                "session_id": self.generate_session_id(),
                "username": username,
                "password": encrypted_password,
                "target_username": target_username,
                "created_at": now,
                "last_used": now,
                "login_attempts": 0,
                "status": "created",
                "cookies": None,
                "fingerprint": None,
                "assigned_proxy": None,
                "cooldown_until": None,
                "cooldown_reason": None,
                "chrome_profile_path": None,
                "last_activity": now,
            }

            self.sessions[session_name] = session_data
            self.save_sessions()
            return session_name, session_data

    def generate_session_id(self) -> str:
        combined = str(time.time()) + base64.b64encode(os.urandom(16)).decode("utf-8")
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

    def get_session(self, session_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if session_name not in self.sessions:
                return None
            session = dict(self.sessions[session_name])
            if session.get("password"):
                decrypted = self.decrypt_data(session["password"])
                if decrypted is not None:
                    session["password"] = decrypted
            return session

    def update_session(self, session_name: str, updates: Dict[str, Any]) -> bool:
        with self._lock:
            if session_name not in self.sessions:
                return False
            payload = dict(updates)
            if "password" in payload and payload["password"] is not None:
                payload["password"] = self.encrypt_data(payload["password"])
            payload["last_used"] = datetime.now().isoformat()
            self.sessions[session_name].update(payload)
            self.save_sessions()
            return True

    def delete_session(self, session_name: str) -> bool:
        with self._lock:
            if session_name in self.sessions:
                del self.sessions[session_name]
                self.save_sessions()
                return True
            return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": name,
                    "username": data.get("username"),
                    "target_username": data.get("target_username"),
                    "created_at": data.get("created_at"),
                    "last_used": data.get("last_used"),
                    "status": data.get("status"),
                    "login_attempts": data.get("login_attempts", 0),
                    "cooldown_until": data.get("cooldown_until"),
                }
                for name, data in self.sessions.items()
            ]

    def find_session_by_username(self, username: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        with self._lock:
            for name, data in self.sessions.items():
                if data.get("username") == username:
                    return name, data
            return None, None

    def is_session_expired(self, session_name: str, hours: int = 24) -> bool:
        with self._lock:
            if session_name not in self.sessions:
                return True
            last_used_str = self.sessions[session_name].get("last_used", "1970-01-01T00:00:00")
            try:
                last_used = datetime.fromisoformat(last_used_str)
            except ValueError:
                return True
            return datetime.now() > (last_used + timedelta(hours=hours))

    def cleanup_expired_sessions(self, hours: int = 24) -> List[str]:
        with self._lock:
            expired = [name for name in list(self.sessions) if self.is_session_expired(name, hours)]
            for name in expired:
                del self.sessions[name]
            if expired:
                self.save_sessions()
            return expired

    def save_chrome_cookies(self, session_name: str, cookies: List[Dict[str, Any]]) -> bool:
        """Lưu cookie trình duyệt dạng JSON mã hóa Fernet (loại bỏ hoàn toàn pickle)."""
        with self._lock:
            if session_name not in self.sessions:
                return False
            try:
                serialized = json.dumps(cookies, ensure_ascii=False)
                encrypted = self.encrypt_data(serialized)
                self.sessions[session_name]["cookies"] = encrypted
                self.sessions[session_name]["last_activity"] = datetime.now().isoformat()
                self.save_sessions()
                return True
            except Exception as exc:
                print(f"[SESSION] ⚠️ Lỗi lưu cookies: {exc}")
                return False

    def load_chrome_cookies(self, session_name: str) -> Optional[List[Dict[str, Any]]]:
        """Giải mã và đọc cookie trình duyệt từ JSON an toàn."""
        with self._lock:
            if session_name not in self.sessions:
                return None
            encrypted = self.sessions[session_name].get("cookies")
            if not encrypted:
                return None
            try:
                decrypted = self.decrypt_data(encrypted)
                if not decrypted:
                    return None
                cookies = json.loads(decrypted)
                return cookies if isinstance(cookies, list) else None
            except Exception as exc:
                print(f"[SESSION] ⚠️ Lỗi load cookies: {exc}")
                return None

    def get_or_init_fingerprint(
        self, session_name: str, factory_fn: Callable[[], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Lấy fingerprint cố định đã lưu của tài khoản hoặc khởi tạo mới và lưu lại."""
        with self._lock:
            session = self.sessions.get(session_name)
            if session and isinstance(session.get("fingerprint"), dict):
                return dict(session["fingerprint"])

            fp = factory_fn()
            if session is not None:
                session["fingerprint"] = fp
                self.save_sessions()
            return fp

    def set_assigned_proxy(self, session_name: str, proxy_url: Optional[str]) -> None:
        with self._lock:
            if session_name in self.sessions:
                self.sessions[session_name]["assigned_proxy"] = proxy_url
                self.save_sessions()

    def get_assigned_proxy(self, session_name: str) -> Optional[str]:
        with self._lock:
            session = self.sessions.get(session_name)
            return session.get("assigned_proxy") if session else None

    def set_account_cooldown(self, session_name: str, minutes: int = 30, reason: str = "") -> None:
        """Đặt thời gian tạm nghỉ khi phát hiện rate limit hoặc checkpoint."""
        with self._lock:
            if session_name not in self.sessions:
                return
            until = (datetime.now() + timedelta(minutes=max(1, minutes))).isoformat()
            self.sessions[session_name]["cooldown_until"] = until
            self.sessions[session_name]["cooldown_reason"] = reason
            self.sessions[session_name]["status"] = "cooldown"
            self.save_sessions()

    def is_in_cooldown(self, session_name: str) -> Tuple[bool, str]:
        with self._lock:
            session = self.sessions.get(session_name)
            if not session:
                return False, ""
            until_str = session.get("cooldown_until")
            if not until_str:
                return False, ""
            try:
                until = datetime.fromisoformat(until_str)
            except ValueError:
                return False, ""

            now = datetime.now()
            if now < until:
                remaining_mins = max(1, int((until - now).total_seconds() // 60) + 1)
                reason = session.get("cooldown_reason") or "safety cooldown"
                return True, f"Tài khoản đang tạm nghỉ ({reason}), còn khoảng {remaining_mins} phút"

            session["cooldown_until"] = None
            session["cooldown_reason"] = None
            self.save_sessions()
            return False, ""

    def record_login_attempt(self, session_name: str, success: bool = False) -> bool:
        with self._lock:
            if session_name not in self.sessions:
                return False
            session = self.sessions[session_name]
            if success:
                session["status"] = "active"
                session["last_successful_login"] = datetime.now().isoformat()
                session["login_attempts"] = 0
                session["cooldown_until"] = None
            else:
                session["login_attempts"] = session.get("login_attempts", 0) + 1
                session["status"] = "login_failed"
                session["last_failed_login"] = datetime.now().isoformat()
            self.save_sessions()
            return True

    def can_attempt_login(
        self, session_name: str, max_attempts: int = 3, cooldown_minutes: int = 30
    ) -> Tuple[bool, str]:
        with self._lock:
            if session_name not in self.sessions:
                return False, "Session không tồn tại"

            in_cooldown, cooldown_msg = self.is_in_cooldown(session_name)
            if in_cooldown:
                return False, cooldown_msg

            session = self.sessions[session_name]
            attempts = session.get("login_attempts", 0)
            if attempts >= max_attempts:
                last_failed = session.get("last_failed_login")
                if last_failed:
                    try:
                        last_failed_time = datetime.fromisoformat(last_failed)
                    except ValueError:
                        last_failed_time = datetime.min
                    cooldown_end = last_failed_time + timedelta(minutes=cooldown_minutes)
                    if datetime.now() < cooldown_end:
                        remaining = cooldown_end - datetime.now()
                        return False, f"Còn {max(1, int(remaining.total_seconds() // 60))} phút cooldown"
                session["login_attempts"] = 0
                self.save_sessions()

            return True, ""

    def save_sessions(self) -> None:
        with self._lock:
            try:
                with open(self.session_file, "w", encoding="utf-8") as f:
                    json.dump(self.sessions, f, indent=2, ensure_ascii=False)
            except Exception as exc:
                print(f"[SESSION] ⚠️ Lỗi lưu sessions: {exc}")

    def load_sessions(self) -> None:
        with self._lock:
            try:
                if os.path.exists(self.session_file):
                    with open(self.session_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    self.sessions = loaded if isinstance(loaded, dict) else {}
                else:
                    self.sessions = {}
            except Exception as exc:
                print(f"[SESSION] ⚠️ Lỗi load sessions: {exc}")
                self.sessions = {}

    def get_session_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self.sessions)
            active = sum(1 for s in self.sessions.values() if s.get("status") == "active")
            failed = sum(1 for s in self.sessions.values() if s.get("status") == "login_failed")
            return {
                "total_sessions": total,
                "active_sessions": active,
                "failed_sessions": failed,
                "success_rate": (active / max(1, total)) * 100.0,
            }

    def print_session_summary(self) -> None:
        stats = self.get_session_stats()
        print("\n[SESSION] 🔐 === SESSION SUMMARY ===")
        print(
            f"[SESSION] 📊 Total: {stats['total_sessions']} | "
            f"Active: {stats['active_sessions']} | Failed: {stats['failed_sessions']}"
        )
        print("[SESSION] ================================\n")


_session_manager: Optional[SessionManager] = None
_session_lock = threading.Lock()


def get_session_manager(
    session_file: Optional[str] = None, key_file: Optional[str] = None
) -> SessionManager:
    global _session_manager
    with _session_lock:
        if _session_manager is None:
            _session_manager = SessionManager(session_file=session_file, key_file=key_file)
        return _session_manager


def reset_session_manager() -> None:
    global _session_manager
    with _session_lock:
        _session_manager = None
