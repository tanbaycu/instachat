from collections import deque
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
import json
import os
import smtplib
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from config.config_manager import get_config_manager, get_data_dir


class NotificationLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    CONSOLE = "console"
    EMAIL = "email"
    FILE = "file"
    WEBHOOK = "webhook"


class NotificationSystem:
    """Hệ thống thông báo đa kênh an toàn đa luồng, không gửi trùng và hỗ trợ tắt sạch."""

    LEVEL_PRIORITY = {"info": 0, "warning": 1, "error": 2, "critical": 3}

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.notifications: deque = deque(maxlen=1000)
        self.subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.channels: Dict[NotificationChannel, Any] = {}
        self.notification_stats: Dict[str, Any] = {
            "total_sent": 0,
            "by_level": {level.value: 0 for level in NotificationLevel},
            "by_channel": {channel.value: 0 for channel in NotificationChannel},
        }
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self.worker_active = False
        self.worker_thread: Optional[threading.Thread] = None
        self.notification_queue: deque = deque()

        self.config = self.load_config()
        self.setup_channels()

    def load_config(self) -> Dict[str, Any]:
        logs_dir = get_data_dir("logs")
        mon_cfg = get_config_manager().get("monitoring", "notifications", {}) or {}
        default_config: Dict[str, Any] = {
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_email": "",
                "to_emails": [],
            },
            "file": {
                "enabled": "file" in mon_cfg.get("channels", ["console", "file"]),
                "log_file": os.path.join(logs_dir, "notifications.log"),
                "max_file_size_mb": 10,
            },
            "console": {
                "enabled": "console" in mon_cfg.get("channels", ["console", "file"]),
                "show_timestamp": True,
                "colored_output": True,
            },
            "webhook": {
                "enabled": False,
                "url": os.getenv("NOTIFICATION_WEBHOOK_URL", ""),
                "headers": {},
            },
            "filters": {
                "min_level": mon_cfg.get("min_level", "info"),
                "keywords_filter": [],
                "rate_limit_per_minute": mon_cfg.get("rate_limit_per_minute", 60),
            },
        }

        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return {**default_config, **loaded}
            except Exception as exc:
                print(f"[NOTIFY] ⚠️ Lỗi đọc config notification: {exc}")

        return default_config

    def setup_channels(self) -> None:
        self.channels.clear()
        if self.config["console"]["enabled"]:
            self.channels[NotificationChannel.CONSOLE] = ConsoleNotifier(self.config["console"])
        if self.config["file"]["enabled"]:
            self.channels[NotificationChannel.FILE] = FileNotifier(self.config["file"])
        if self.config["email"]["enabled"]:
            self.channels[NotificationChannel.EMAIL] = EmailNotifier(self.config["email"])
        if self.config["webhook"]["enabled"] and self.config["webhook"].get("url"):
            self.channels[NotificationChannel.WEBHOOK] = WebhookNotifier(self.config["webhook"])

    def send_notification(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        context: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = time.time()
        notification = {
            "id": self.generate_notification_id(now),
            "timestamp": datetime.now().isoformat(),
            "epoch_ts": now,
            "message": message,
            "level": level.value,
            "context": context,
            "metadata": metadata or {},
        }

        if not self.should_send_notification(notification):
            return False

        # CRITICAL xử lý trực tiếp ngay lập tức và KHÔNG đẩy vào queue để tránh gửi 2 lần.
        if level == NotificationLevel.CRITICAL:
            self.process_notification(notification)
        else:
            with self._lock:
                self.notification_queue.append(notification)
                if not self.worker_active:
                    self.start_worker()
            self._wake_event.set()

        return True

    def should_send_notification(self, notification: Dict[str, Any]) -> bool:
        min_level = self.config["filters"]["min_level"]
        if self.LEVEL_PRIORITY.get(notification["level"], 0) < self.LEVEL_PRIORITY.get(min_level, 0):
            return False

        keywords_filter = self.config["filters"]["keywords_filter"]
        if keywords_filter:
            msg_lower = notification["message"].lower()
            if not any(kw.lower() in msg_lower for kw in keywords_filter):
                return False

        return self.check_rate_limit()

    def check_rate_limit(self) -> bool:
        rate_limit = self.config["filters"]["rate_limit_per_minute"]
        if rate_limit <= 0:
            return True

        current_time = time.time()
        with self._lock:
            recent = sum(
                1 for item in self.notifications if (current_time - item.get("epoch_ts", 0)) < 60
            )
        return recent < rate_limit

    def generate_notification_id(self, epoch_ts: Optional[float] = None) -> str:
        ts = epoch_ts if epoch_ts is not None else time.time()
        return f"notif_{int(ts * 1000)}"

    def start_worker(self) -> None:
        with self._lock:
            if self.worker_active:
                return
            self._stop_event.clear()
            self.worker_active = True
            self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
            self.worker_thread.start()

    def worker_loop(self) -> None:
        while not self._stop_event.is_set():
            notification = None
            with self._lock:
                if self.notification_queue:
                    notification = self.notification_queue.popleft()
                else:
                    self._wake_event.clear()

            if notification is not None:
                self.process_notification(notification)
            else:
                self._wake_event.wait(timeout=0.5)

        # Xử lý nốt phần còn lại trong queue trước khi dừng hẳn
        while True:
            with self._lock:
                if not self.notification_queue:
                    break
                notification = self.notification_queue.popleft()
            self.process_notification(notification)

    def process_notification(self, notification: Dict[str, Any]) -> None:
        try:
            with self._lock:
                self.notifications.append(notification)
                channels_snapshot = list(self.channels.items())

            for channel_type, channel in channels_snapshot:
                try:
                    channel.send(notification)
                    with self._lock:
                        self.notification_stats["by_channel"][channel_type.value] += 1
                except Exception as exc:
                    print(f"[NOTIFY] ❌ Lỗi gửi qua {channel_type.value}: {exc}")

            with self._lock:
                self.notification_stats["total_sent"] += 1
                self.notification_stats["by_level"][notification["level"]] += 1

            self.notify_subscribers(notification)
        except Exception as exc:
            print(f"[NOTIFY] ❌ Lỗi xử lý notification: {exc}")

    def notify_subscribers(self, notification: Dict[str, Any]) -> None:
        level = notification["level"]
        with self._lock:
            callbacks_to_call: List[Callable[[Dict[str, Any]], None]] = []
            for sub_level, callbacks in self.subscribers.items():
                if self.should_notify_subscriber(level, sub_level):
                    callbacks_to_call.extend(list(callbacks))

        for callback in callbacks_to_call:
            try:
                callback(notification)
            except Exception as exc:
                print(f"[NOTIFY] ❌ Lỗi subscriber callback: {exc}")

    def should_notify_subscriber(self, notification_level: str, subscriber_level: str) -> bool:
        return self.LEVEL_PRIORITY.get(notification_level, 0) >= self.LEVEL_PRIORITY.get(
            subscriber_level, 0
        )

    def subscribe(self, callback: Callable[[Dict[str, Any]], None], level: NotificationLevel = NotificationLevel.INFO) -> None:
        with self._lock:
            self.subscribers.setdefault(level.value, []).append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None], level: NotificationLevel = NotificationLevel.INFO) -> None:
        with self._lock:
            if level.value in self.subscribers:
                try:
                    self.subscribers[level.value].remove(callback)
                except ValueError:
                    pass

    def get_recent_notifications(
        self, hours: int = 24, level: Optional[NotificationLevel] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        with self._lock:
            snapshot = list(self.notifications)

        recent = []
        for notif in snapshot:
            try:
                notif_time = datetime.fromisoformat(notif["timestamp"])
            except ValueError:
                continue
            if notif_time > cutoff_time:
                if level is None or notif["level"] == level.value:
                    recent.append({k: v for k, v in notif.items() if k != "epoch_ts"})
        return recent[-limit:]

    def get_notification_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_sent": self.notification_stats["total_sent"],
                "by_level": dict(self.notification_stats["by_level"]),
                "by_channel": dict(self.notification_stats["by_channel"]),
                "queue_size": len(self.notification_queue),
                "history_size": len(self.notifications),
                "active_channels": len(self.channels),
                "subscribers_count": sum(len(v) for v in self.subscribers.values()),
            }

    def print_notification_summary(self) -> None:
        stats = self.get_notification_stats()
        print("\n[NOTIFY] 🔔 === NOTIFICATION SUMMARY ===")
        print(f"[NOTIFY] 📊 Total Sent: {stats['total_sent']} | History: {stats['history_size']}")
        for level, count in stats["by_level"].items():
            if count > 0:
                print(f"[NOTIFY]   - {level.upper()}: {count}")
        print("[NOTIFY] =====================================\n")

    def stop(self) -> None:
        with self._lock:
            self.worker_active = False
            self._stop_event.set()
            self._wake_event.set()
            thread = self.worker_thread
            self.worker_thread = None

        if thread and thread.is_alive():
            thread.join(timeout=2.0)


class ConsoleNotifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.colors = {
            "info": "\033[94m",
            "warning": "\033[93m",
            "error": "\033[91m",
            "critical": "\033[95m",
            "reset": "\033[0m",
        }

    def send(self, notification: Dict[str, Any]) -> None:
        level = notification["level"]
        message = notification["message"]
        context = notification["context"]

        prefix = ""
        if self.config.get("show_timestamp", True):
            ts = datetime.fromisoformat(notification["timestamp"]).strftime("%H:%M:%S")
            prefix = f"[{ts}] "

        if self.config.get("colored_output", True):
            level_str = f"{self.colors.get(level, '')}[{level.upper()}]{self.colors['reset']}"
        else:
            level_str = f"[{level.upper()}]"

        output = f"{prefix}{level_str} {message}"
        if context:
            output += f" ({context})"
        print(output)


class FileNotifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.log_file = config["log_file"]
        os.makedirs(os.path.dirname(self.log_file) or ".", exist_ok=True)
        self._lock = threading.Lock()

    def send(self, notification: Dict[str, Any]) -> None:
        log_entry = {
            "timestamp": notification["timestamp"],
            "level": notification["level"],
            "message": notification["message"],
            "context": notification["context"],
            "metadata": notification.get("metadata", {}),
        }
        with self._lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                self.rotate_log_if_needed()
            except Exception as exc:
                print(f"[NOTIFY] ❌ File notification error: {exc}")

    def rotate_log_if_needed(self) -> None:
        max_size = self.config.get("max_file_size_mb", 10) * 1024 * 1024
        if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > max_size:
            backup_file = f"{self.log_file}.backup"
            if os.path.exists(backup_file):
                os.remove(backup_file)
            os.rename(self.log_file, backup_file)


class EmailNotifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def send(self, notification: Dict[str, Any]) -> None:
        if not self.config.get("to_emails"):
            return
        msg = MIMEMultipart()
        msg["From"] = self.config["from_email"]
        msg["To"] = ", ".join(self.config["to_emails"])
        msg["Subject"] = f"[{notification['level'].upper()}] InstaChat Notification"
        body = (
            f"Level: {notification['level'].upper()}\n"
            f"Time: {notification['timestamp']}\n"
            f"Context: {notification['context']}\n"
            f"Message: {notification['message']}\n"
            f"Metadata: {json.dumps(notification.get('metadata', {}), indent=2, ensure_ascii=False)}\n"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(self.config["smtp_server"], self.config["smtp_port"], timeout=10) as server:
            server.starttls()
            server.login(self.config["username"], self.config["password"])
            server.sendmail(self.config["from_email"], self.config["to_emails"], msg.as_string())


class WebhookNotifier:
    """Hỗ trợ Discord (`content`), Slack (`text`) và Generic JSON webhook."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def send(self, notification: Dict[str, Any]) -> None:
        import requests

        summary = f"[{notification['level'].upper()}] ({notification.get('context') or 'bot'}) {notification['message']}"
        payload = {
            "content": summary,
            "text": summary,
            "notification": {k: v for k, v in notification.items() if k != "epoch_ts"},
            "timestamp": notification["timestamp"],
            "source": "InstaChat",
        }
        headers = {**self.config.get("headers", {}), "Content-Type": "application/json"}
        response = requests.post(self.config["url"], json=payload, headers=headers, timeout=10)
        response.raise_for_status()


_notification_system: Optional[NotificationSystem] = None
_notif_lock = threading.Lock()


def get_notification_system(config_file: Optional[str] = None) -> NotificationSystem:
    global _notification_system
    with _notif_lock:
        if _notification_system is None:
            _notification_system = NotificationSystem(config_file=config_file)
        return _notification_system


def reset_notification_system() -> None:
    global _notification_system
    with _notif_lock:
        if _notification_system is not None:
            _notification_system.stop()
        _notification_system = None


def notify_info(message: str, context: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
    return get_notification_system().send_notification(message, NotificationLevel.INFO, context, metadata)


def notify_warning(message: str, context: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
    return get_notification_system().send_notification(message, NotificationLevel.WARNING, context, metadata)


def notify_error(message: str, context: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
    return get_notification_system().send_notification(message, NotificationLevel.ERROR, context, metadata)


def notify_critical(message: str, context: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
    return get_notification_system().send_notification(message, NotificationLevel.CRITICAL, context, metadata)
