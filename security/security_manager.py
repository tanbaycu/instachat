from collections import defaultdict, deque
from datetime import datetime
from functools import wraps
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from config.config_manager import get_config_manager, get_data_dir


class SecurityManager:
    """Bảo vệ inbound (chống spam/rate-limit từ user) và outbound safety budget cho tài khoản Instagram."""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.message_history: deque = deque(maxlen=1000)
        self.rate_limits: Dict[str, List[float]] = defaultdict(list)
        self.outbound_timestamps: Dict[str, List[float]] = defaultdict(list)
        self.spam_scores: Dict[str, float] = defaultdict(float)
        self.blocked_users = set()
        self._lock = threading.RLock()

        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        cfg = get_config_manager().get("security") or {}
        default_config: Dict[str, Any] = {
            "rate_limits": {
                "messages_per_minute": cfg.get("rate_limiting", {}).get("messages_per_minute", 30),
                "messages_per_hour": cfg.get("rate_limiting", {}).get("messages_per_hour", 200),
                "ai_requests_per_minute": cfg.get("rate_limiting", {}).get("ai_requests_per_minute", 15),
                "image_requests_per_hour": cfg.get("rate_limiting", {}).get("image_requests_per_hour", 20),
            },
            "outbound_limits": {
                "enabled": cfg.get("outbound_limits", {}).get("enabled", True),
                "messages_per_minute": cfg.get("outbound_limits", {}).get("messages_per_minute", 6),
                "messages_per_hour": cfg.get("outbound_limits", {}).get("messages_per_hour", 60),
                "messages_per_day": cfg.get("outbound_limits", {}).get("messages_per_day", 300),
                "min_seconds_between_replies": cfg.get("outbound_limits", {}).get(
                    "min_seconds_between_replies", 4.0
                ),
            },
            "spam_detection": {
                "max_duplicate_messages": cfg.get("spam_detection", {}).get("max_duplicate_messages", 3),
                "max_similar_messages": cfg.get("spam_detection", {}).get("max_similar_messages", 5),
                "spam_keywords": ["spam", "bot", "fake", "scam", "hack"],
                "suspicious_patterns": [
                    r"\b(click|visit|go to)\s+https?://",
                    r"\b(free|win|prize|money)\b.*\b(click|visit|link)\b",
                    r"\b(urgent|limited time|act now)\b",
                ],
            },
            "account_protection": {
                "max_login_attempts": cfg.get("account_protection", {}).get("max_login_attempts", 3),
                "cooldown_minutes": cfg.get("account_protection", {}).get("cooldown_minutes", 30),
                "suspicious_activity_threshold": 10,
            },
            "content_filter": {
                "blocked_keywords": cfg.get("content_filtering", {}).get(
                    "blocked_keywords", ["hate", "violence", "illegal"]
                ),
                "max_message_length": cfg.get("content_filtering", {}).get("max_message_length", 1000),
                "allow_links": cfg.get("content_filtering", {}).get("allow_links", False),
            },
        }

        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return {**default_config, **loaded}
            except Exception as exc:
                print(f"[SECURITY] ⚠️ Lỗi load config: {exc}")

        return default_config

    def check_rate_limit(self, user_id: str, action_type: str = "message") -> Tuple[bool, str]:
        current_time = time.time()
        limits = self.config["rate_limits"]

        if action_type == "message":
            per_minute = limits["messages_per_minute"]
            per_hour = limits["messages_per_hour"]
        elif action_type == "ai_request":
            per_minute = limits["ai_requests_per_minute"]
            per_hour = per_minute * 6
        elif action_type == "image_request":
            per_minute = 2
            per_hour = limits["image_requests_per_hour"]
        else:
            per_minute = 10
            per_hour = 100

        with self._lock:
            cutoff = current_time - 3600
            self.rate_limits[user_id] = [t for t in self.rate_limits[user_id] if t > cutoff]
            recent = [t for t in self.rate_limits[user_id] if t > current_time - 60]
            hourly = self.rate_limits[user_id]

            if len(recent) >= per_minute:
                return False, f"Quá nhiều {action_type} trong 1 phút. Vui lòng chờ."
            if len(hourly) >= per_hour:
                return False, f"Quá nhiều {action_type} trong 1 giờ. Vui lòng chờ."

            self.rate_limits[user_id].append(current_time)
            return True, ""

    def check_outbound_budget(
        self, account_id: str = "default", now: Optional[float] = None
    ) -> Tuple[bool, str]:
        """Kiểm soát tần suất gửi tin đi của tài khoản Instagram để tránh checkpoint/rate-limit."""
        limits = self.config.get("outbound_limits", {})
        if not limits.get("enabled", True):
            return True, ""

        current_time = now if now is not None else time.time()
        min_gap = float(limits.get("min_seconds_between_replies", 4.0))
        max_per_min = int(limits.get("messages_per_minute", 6))
        max_per_hour = int(limits.get("messages_per_hour", 60))
        max_per_day = int(limits.get("messages_per_day", 300))

        with self._lock:
            cutoff_day = current_time - 86400
            timestamps = [t for t in self.outbound_timestamps[account_id] if t > cutoff_day]
            self.outbound_timestamps[account_id] = timestamps

            if timestamps and (current_time - timestamps[-1]) < min_gap:
                wait_sec = min_gap - (current_time - timestamps[-1])
                return False, f"Cần nghỉ tối thiểu {wait_sec:.1f}s trước khi gửi tiếp"

            per_min_cnt = sum(1 for t in timestamps if t > current_time - 60)
            if per_min_cnt >= max_per_min:
                return False, f"Đạt ngưỡng outbound {max_per_min} tin/phút"

            per_hour_cnt = sum(1 for t in timestamps if t > current_time - 3600)
            if per_hour_cnt >= max_per_hour:
                return False, f"Đạt ngưỡng outbound {max_per_hour} tin/giờ"

            if len(timestamps) >= max_per_day:
                return False, f"Đạt ngưỡng outbound {max_per_day} tin/ngày"

            return True, ""

    def record_outbound_action(
        self, account_id: str = "default", now: Optional[float] = None
    ) -> None:
        current_time = now if now is not None else time.time()
        with self._lock:
            cutoff_day = current_time - 86400
            timestamps = [t for t in self.outbound_timestamps[account_id] if t > cutoff_day]
            timestamps.append(current_time)
            timestamps.sort()
            self.outbound_timestamps[account_id] = timestamps

    def get_outbound_budget_status(
        self, account_id: str = "default", now: Optional[float] = None
    ) -> Dict[str, Any]:
        limits = self.config.get("outbound_limits", {})
        current_time = now if now is not None else time.time()
        with self._lock:
            cutoff_day = current_time - 86400
            timestamps = [t for t in self.outbound_timestamps[account_id] if t > cutoff_day]
            self.outbound_timestamps[account_id] = timestamps

            sent_min = sum(1 for t in timestamps if t > current_time - 60)
            sent_hour = sum(1 for t in timestamps if t > current_time - 3600)
            sent_day = len(timestamps)

        return {
            "enabled": bool(limits.get("enabled", True)),
            "sent_last_minute": sent_min,
            "limit_per_minute": int(limits.get("messages_per_minute", 6)),
            "sent_last_hour": sent_hour,
            "limit_per_hour": int(limits.get("messages_per_hour", 60)),
            "sent_last_day": sent_day,
            "limit_per_day": int(limits.get("messages_per_day", 300)),
            "min_seconds_between_replies": float(limits.get("min_seconds_between_replies", 4.0)),
        }

    def detect_spam(self, message: str, user_id: str) -> Tuple[bool, float, List[str]]:
        spam_score = 0.0
        reasons: List[str] = []

        with self._lock:
            user_messages = [msg for msg in self.message_history if msg.get("user_id") == user_id]
            recent_messages = [msg["content"] for msg in user_messages[-10:]]

            duplicate_count = recent_messages.count(message)
            if duplicate_count >= self.config["spam_detection"]["max_duplicate_messages"]:
                spam_score += 35
                reasons.append("Tin nhắn trùng lặp")

            similar_count = sum(1 for msg in recent_messages if self.similarity(message, msg) > 0.8)
            if similar_count >= self.config["spam_detection"]["max_similar_messages"]:
                spam_score += 20
                reasons.append("Tin nhắn tương tự")

            spam_keywords = self.config["spam_detection"]["spam_keywords"]
            keyword_matches = sum(1 for kw in spam_keywords if kw.lower() in message.lower())
            if keyword_matches > 0:
                spam_score += keyword_matches * 10
                reasons.append("Chứa từ khóa spam")

            pattern_matches = sum(
                1
                for pattern in self.config["spam_detection"]["suspicious_patterns"]
                if re.search(pattern, message, re.IGNORECASE)
            )
            if pattern_matches > 0:
                spam_score += pattern_matches * 20
                reasons.append("Pattern đáng nghi")

            if len(message) > self.config["content_filter"]["max_message_length"]:
                spam_score += 10
                reasons.append("Tin nhắn quá dài")

            if not self.config["content_filter"]["allow_links"] and re.search(r"https?://", message):
                spam_score += 25
                reasons.append("Chứa link")

            if len(message) > 20 and message.isupper():
                spam_score += 15
                reasons.append("Toàn chữ hoa")

            self.spam_scores[user_id] = (self.spam_scores[user_id] * 0.9) + (spam_score * 0.1)
            is_spam = spam_score > 50 or self.spam_scores[user_id] > 30
            return is_spam, spam_score, reasons

    def similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        union = words1.union(words2)
        return len(words1.intersection(words2)) / len(union) if union else 0.0

    def check_content_filter(self, message: str) -> Tuple[bool, str]:
        blocked_keywords = self.config["content_filter"]["blocked_keywords"]
        msg_lower = message.lower()
        for keyword in blocked_keywords:
            if keyword.lower() in msg_lower:
                return False, "Tin nhắn chứa nội dung không được phép"
        return True, ""

    def log_message(
        self, message: str, user_id: str, response: str = "", action_taken: str = ""
    ) -> None:
        with self._lock:
            self.message_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id,
                    "content": message,
                    "response": response,
                    "action_taken": action_taken,
                    "spam_score": self.spam_scores.get(user_id, 0.0),
                }
            )

    def is_user_blocked(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self.blocked_users

    def block_user(self, user_id: str, reason: str = "") -> None:
        with self._lock:
            self.blocked_users.add(user_id)
            print(f"[SECURITY] 🚫 User blocked: {user_id} - {reason}")

    def unblock_user(self, user_id: str) -> None:
        with self._lock:
            self.blocked_users.discard(user_id)

    def validate_message(self, message: str, user_id: str) -> Tuple[bool, str]:
        if not message or not str(message).strip():
            return False, "Tin nhắn rỗng"

        if self.is_user_blocked(user_id):
            return False, "User đã bị block"

        rate_ok, rate_msg = self.check_rate_limit(user_id, "message")
        if not rate_ok:
            return False, rate_msg

        content_ok, content_msg = self.check_content_filter(message)
        if not content_ok:
            return False, content_msg

        is_spam, spam_score, _ = self.detect_spam(message, user_id)
        if is_spam:
            if spam_score > 80:
                self.block_user(user_id, f"Spam score: {spam_score}")
                return False, "User đã bị block do spam"
            return False, f"Tin nhắn bị từ chối do spam (score: {spam_score})"

        return True, ""

    def get_security_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_messages = len(self.message_history)
            spam_messages = sum(
                1 for msg in self.message_history if msg.get("spam_score", 0) > 30
            )
            return {
                "total_messages": total_messages,
                "spam_messages": spam_messages,
                "blocked_users": len(self.blocked_users),
                "active_rate_limits": len(self.rate_limits),
                "spam_rate": (spam_messages / max(1, total_messages)) * 100.0,
                "avg_spam_score": (
                    sum(self.spam_scores.values()) / max(1, len(self.spam_scores))
                ),
            }

    def print_security_summary(self) -> None:
        stats = self.get_security_stats()
        print("\n[SECURITY] 🔐 === SECURITY SUMMARY ===")
        print(
            f"[SECURITY] 📊 Total: {stats['total_messages']} | "
            f"Spam: {stats['spam_messages']} ({stats['spam_rate']:.1f}%) | "
            f"Blocked: {stats['blocked_users']}"
        )
        print("[SECURITY] ===================================\n")

    def save_security_report(self, filename: Optional[str] = None) -> bool:
        target = filename or os.path.join(get_data_dir("logs"), "security_report.json")
        try:
            with self._lock:
                report = {
                    "timestamp": datetime.now().isoformat(),
                    "stats": self.get_security_stats(),
                    "outbound_budget": self.get_outbound_budget_status(),
                    "blocked_users": list(self.blocked_users),
                    "recent_messages": list(self.message_history)[-50:],
                    "config": self.config,
                }
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            print(f"[SECURITY] ❌ Lỗi lưu báo cáo: {exc}")
            return False


_security_manager: Optional[SecurityManager] = None
_security_lock = threading.Lock()


def get_security_manager(config_file: Optional[str] = None) -> SecurityManager:
    global _security_manager
    with _security_lock:
        if _security_manager is None:
            _security_manager = SecurityManager(config_file=config_file)
        return _security_manager


def reset_security_manager() -> None:
    global _security_manager
    with _security_lock:
        _security_manager = None


def security_check(func):
    @wraps(func)
    def wrapper(self, message, user_id="unknown", *args, **kwargs):
        security_manager = get_security_manager()
        is_valid, error_msg = security_manager.validate_message(message, user_id)
        if not is_valid:
            return error_msg
        try:
            result = func(self, message, user_id, *args, **kwargs)
            security_manager.log_message(message, user_id, str(result)[:100], "processed")
            return result
        except Exception as exc:
            security_manager.log_message(message, user_id, "", f"error: {exc}")
            raise

    return wrapper
