from datetime import datetime
from enum import Enum
from functools import wraps
import json
import logging
import os
import random
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

from config.config_manager import get_data_dir


class InstaChatError(Exception):
    """Base exception cho toàn bộ hệ thống InstaChat."""


class InstagramRateLimitError(InstaChatError):
    """Phát sinh khi Instagram tạm thời giới hạn tần suất thao tác."""


class InstagramCheckpointError(InstaChatError):
    """Phát sinh khi tài khoản Instagram gặp checkpoint / xác minh bất thường."""


class InstagramAuthError(InstaChatError):
    """Phát sinh khi thông tin đăng nhập sai hoặc yêu cầu xác thực thất bại."""


class SessionExpiredError(InstaChatError):
    """Phát sinh khi cookie/phiên đăng nhập Instagram không còn hiệu lực."""


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorHandler:
    """Quản lý ghi nhận, phân loại và gợi ý phục hồi lỗi an toàn đa luồng."""

    def __init__(self, log_file: Optional[str] = None):
        logs_dir = get_data_dir("logs")
        self.log_file = log_file or os.path.join(logs_dir, "error_logs.json")
        self.text_log_file = os.path.join(os.path.dirname(self.log_file) or logs_dir, "error_handler.log")
        self.error_counts: Dict[str, int] = {}
        self.recent_errors: List[Dict[str, Any]] = []
        self.max_recent_errors = 50
        self._lock = threading.RLock()

        os.makedirs(os.path.dirname(self.log_file) or logs_dir, exist_ok=True)
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Khởi tạo logger riêng để không làm trùng handler của root logger."""
        logger = logging.getLogger("instachat.error_handler")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        # Xóa handler cũ nếu tạo mới instance (ví dụ trong lúc test với tmp_path)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler(self.text_log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        return logger

    def log_error(
        self,
        error: BaseException,
        context: str = "",
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        user_message: str = "",
    ) -> Dict[str, Any]:
        """Ghi lại thông tin lỗi và lưu vào file JSON theo giới hạn 1000 bản ghi."""
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "severity": severity.value,
            "user_message": user_message,
            "traceback": traceback.format_exc(),
        }

        with self._lock:
            error_type = error_info["error_type"]
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
            self.recent_errors.append(error_info)
            if len(self.recent_errors) > self.max_recent_errors:
                self.recent_errors.pop(0)

            if severity == ErrorSeverity.CRITICAL:
                self.logger.critical(f"CRITICAL ERROR in {context}: {error}")
            elif severity == ErrorSeverity.HIGH:
                self.logger.error(f"HIGH ERROR in {context}: {error}")
            elif severity == ErrorSeverity.MEDIUM:
                self.logger.warning(f"MEDIUM ERROR in {context}: {error}")
            else:
                self.logger.info(f"LOW ERROR in {context}: {error}")

            self.save_error_log(error_info)

        return error_info

    def save_error_log(self, error_info: Dict[str, Any]) -> None:
        """Ghi log lỗi vào JSON một cách an toàn."""
        with self._lock:
            try:
                logs: List[Dict[str, Any]] = []
                if os.path.exists(self.log_file):
                    with open(self.log_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            logs = loaded

                logs.append(error_info)
                if len(logs) > 1000:
                    logs = logs[-1000:]

                with open(self.log_file, "w", encoding="utf-8") as f:
                    json.dump(logs, f, indent=2, ensure_ascii=False)
            except Exception as exc:
                self.logger.error(f"Không thể lưu error log: {exc}")

    def get_error_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_errors = sum(self.error_counts.values())
            severity_counts = {sev.value: 0 for sev in ErrorSeverity}
            for err in self.recent_errors:
                sev = err.get("severity", "medium")
                if sev in severity_counts:
                    severity_counts[sev] += 1

            return {
                "total_errors": total_errors,
                "error_types": dict(self.error_counts),
                "severity_distribution": severity_counts,
                "recent_errors_count": len(self.recent_errors),
                "most_common_error": (
                    max(self.error_counts.items(), key=lambda x: x[1])
                    if self.error_counts
                    else None
                ),
            }

    def get_recovery_suggestion(self, error_type: str) -> List[str]:
        suggestions = {
            "InstagramRateLimitError": [
                "Tạm dừng gửi tin nhắn và tăng khoảng nghỉ giữa các lượt trả lời",
                "Giảm OUTBOUND_MESSAGES_PER_HOUR trong .env",
                "Kiểm tra proxy đang gán cho tài khoản",
            ],
            "InstagramCheckpointError": [
                "Dừng bot ngay để tránh khóa tài khoản",
                "Mở trình duyệt với profile đã lưu hoặc đăng nhập thủ công để xác minh",
            ],
            "InstagramAuthError": [
                "Kiểm tra lại INSTAGRAM_USERNAME và INSTAGRAM_PASSWORD",
                "Xác minh tài khoản có bật 2FA hay không",
            ],
            "ConnectionError": [
                "Kiểm tra kết nối internet hoặc proxy",
                "Thử lại sau 5-10 giây",
            ],
            "TimeoutException": [
                "Tăng timeout hoặc kiểm tra tốc độ mạng/proxy",
                "Kiểm tra selector giao diện Instagram",
            ],
            "NoSuchElementException": [
                "Instagram có thể đã thay đổi DOM/UI",
                "Cập nhật selector trong automation/selectors.py",
            ],
            "StaleElementReferenceException": [
                "Truy vấn lại element trước khi tương tác",
            ],
            "WebDriverException": [
                "Khởi động lại ChromeDriver",
                "Kiểm tra phiên bản Chrome/Chromium trên hệ thống",
            ],
        }
        return suggestions.get(error_type, ["Kiểm tra logs chi tiết trong data/logs/", "Thử khởi động lại bot"])

    def should_retry(self, error_type: str, attempt_count: int, max_attempts: int = 3) -> bool:
        """Không retry các lỗi nghiêm trọng liên quan đến checkpoint, auth hoặc sai tham số."""
        no_retry_errors = {
            "KeyboardInterrupt",
            "SystemExit",
            "MemoryError",
            "SyntaxError",
            "IndentationError",
            "ValueError",
            "InstagramCheckpointError",
            "InstagramAuthError",
        }
        if error_type in no_retry_errors:
            return False
        if attempt_count >= max_attempts - 1:
            return False
        return True

    def get_retry_delay(self, attempt_count: int, base_delay: float = 1.0) -> float:
        """Exponential backoff kèm jitter ngẫu nhiên để tránh gửi request đồng loạt."""
        delay = min(base_delay * (2**attempt_count), 30.0)
        return delay + random.uniform(0.0, 0.5)

    def print_error_summary(self) -> None:
        stats = self.get_error_stats()
        print("\n[ERROR] 🛡️ === ERROR SUMMARY ===")
        print(f"[ERROR] 📊 Total Errors: {stats['total_errors']}")
        if stats["most_common_error"]:
            etype, count = stats["most_common_error"]
            print(f"[ERROR] 🔥 Most Common: {etype} ({count} times)")
        for severity, count in stats["severity_distribution"].items():
            if count > 0:
                print(f"[ERROR]   - {severity.upper()}: {count}")
        print("[ERROR] ================================\n")

    def close(self) -> None:
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)


_error_handler: Optional[ErrorHandler] = None
_error_handler_lock = threading.Lock()


def get_error_handler(log_file: Optional[str] = None) -> ErrorHandler:
    global _error_handler
    with _error_handler_lock:
        if _error_handler is None:
            _error_handler = ErrorHandler(log_file=log_file)
        return _error_handler


def reset_error_handler() -> None:
    global _error_handler
    with _error_handler_lock:
        if _error_handler is not None:
            _error_handler.close()
        _error_handler = None


def retry_on_error(max_attempts: int = 3, delay: float = 1.0, exceptions=(Exception,)):
    """Decorator retry với exponential backoff + jitter, bỏ qua lỗi checkpoint/auth."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = get_error_handler()
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    error_type = type(exc).__name__
                    severity = ErrorSeverity.MEDIUM if attempt < max_attempts - 1 else ErrorSeverity.HIGH
                    handler.log_error(
                        exc,
                        context=f"{func.__name__} (attempt {attempt + 1}/{max_attempts})",
                        severity=severity,
                    )
                    if not handler.should_retry(error_type, attempt, max_attempts):
                        raise
                    retry_delay = handler.get_retry_delay(attempt, base_delay=delay)
                    print(f"[ERROR] 🔄 Retry {attempt + 1}/{max_attempts} sau {retry_delay:.2f}s...")
                    time.sleep(retry_delay)
            return None

        return wrapper

    return decorator


def log_errors(severity: ErrorSeverity = ErrorSeverity.MEDIUM, context: str = ""):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                get_error_handler().log_error(exc, context=context or func.__name__, severity=severity)
                raise

        return wrapper

    return decorator


class ErrorContext:
    def __init__(self, context: str = "", severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        self.context = context
        self.severity = severity
        self.error_handler = get_error_handler()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and exc_val is not None:
            self.error_handler.log_error(exc_val, context=self.context, severity=self.severity)
        return False
