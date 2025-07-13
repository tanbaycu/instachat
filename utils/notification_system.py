import json
import os
import time
import threading
from datetime import datetime, timedelta
from collections import deque
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


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
    def __init__(self, config_file="utils/notifications_config.json"):
        self.config_file = config_file
        self.notifications = deque(maxlen=1000)
        self.subscribers = {}
        self.channels = {}
        self.notification_stats = {
            'total_sent': 0,
            'by_level': {level.value: 0 for level in NotificationLevel},
            'by_channel': {channel.value: 0 for channel in NotificationChannel}
        }
        
        # Load config
        self.config = self.load_config()
        
        # Setup channels
        self.setup_channels()
        
        # Background worker
        self.worker_active = False
        self.notification_queue = deque()
        self.queue_lock = threading.Lock()
        
        print("[NOTIFY] 🔔 Notification System đã khởi tạo")

    def load_config(self):
        """Load notification configuration"""
        default_config = {
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_email": "",
                "to_emails": []
            },
            "file": {
                "enabled": True,
                "log_file": "utils/notifications.log",
                "max_file_size_mb": 10
            },
            "console": {
                "enabled": True,
                "show_timestamp": True,
                "colored_output": True
            },
            "webhook": {
                "enabled": False,
                "url": "",
                "headers": {}
            },
            "filters": {
                "min_level": "info",
                "keywords_filter": [],
                "rate_limit_per_minute": 60
            }
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return {**default_config, **config}
            else:
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                return default_config
        except Exception as e:
            print(f"[NOTIFY] ⚠️ Lỗi load config: {str(e)}")
            return default_config

    def setup_channels(self):
        """Setup notification channels"""
        # Console channel
        if self.config["console"]["enabled"]:
            self.channels[NotificationChannel.CONSOLE] = ConsoleNotifier(self.config["console"])
        
        # File channel
        if self.config["file"]["enabled"]:
            self.channels[NotificationChannel.FILE] = FileNotifier(self.config["file"])
        
        # Email channel
        if self.config["email"]["enabled"]:
            self.channels[NotificationChannel.EMAIL] = EmailNotifier(self.config["email"])
        
        # Webhook channel
        if self.config["webhook"]["enabled"]:
            self.channels[NotificationChannel.WEBHOOK] = WebhookNotifier(self.config["webhook"])

    def send_notification(self, message, level=NotificationLevel.INFO, context="", metadata=None):
        """Gửi notification"""
        notification = {
            'id': self.generate_notification_id(),
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'level': level.value,
            'context': context,
            'metadata': metadata or {}
        }
        
        # Kiểm tra filters
        if not self.should_send_notification(notification):
            return False
        
        # Thêm vào queue
        with self.queue_lock:
            self.notification_queue.append(notification)
        
        # Process ngay lập tức cho critical notifications
        if level == NotificationLevel.CRITICAL:
            self.process_notification(notification)
        else:
            # Start worker nếu chưa active
            if not self.worker_active:
                self.start_worker()
        
        return True

    def should_send_notification(self, notification):
        """Kiểm tra có nên gửi notification không"""
        # Level filter
        min_level = self.config["filters"]["min_level"]
        level_priority = {"info": 0, "warning": 1, "error": 2, "critical": 3}
        
        if level_priority[notification['level']] < level_priority[min_level]:
            return False
        
        # Keywords filter
        keywords_filter = self.config["filters"]["keywords_filter"]
        if keywords_filter:
            message_lower = notification['message'].lower()
            if not any(keyword.lower() in message_lower for keyword in keywords_filter):
                return False
        
        # Rate limiting
        return self.check_rate_limit()

    def check_rate_limit(self):
        """Kiểm tra rate limit"""
        rate_limit = self.config["filters"]["rate_limit_per_minute"]
        if rate_limit <= 0:
            return True
        
        current_time = time.time()
        recent_notifications = [
            n for n in self.notifications
            if current_time - time.mktime(datetime.fromisoformat(n['timestamp']).timetuple()) < 60
        ]
        
        return len(recent_notifications) < rate_limit

    def generate_notification_id(self):
        """Tạo notification ID unique"""
        return f"notif_{int(time.time() * 1000)}"

    def start_worker(self):
        """Bắt đầu background worker"""
        if self.worker_active:
            return
        
        self.worker_active = True
        worker_thread = threading.Thread(target=self.worker_loop)
        worker_thread.daemon = True
        worker_thread.start()

    def worker_loop(self):
        """Worker loop xử lý notifications"""
        while self.worker_active:
            try:
                with self.queue_lock:
                    if self.notification_queue:
                        notification = self.notification_queue.popleft()
                    else:
                        notification = None
                
                if notification:
                    self.process_notification(notification)
                else:
                    time.sleep(0.1)  # Short sleep when queue is empty
                    
            except Exception as e:
                print(f"[NOTIFY] ❌ Worker error: {str(e)}")
                time.sleep(1)

    def process_notification(self, notification):
        """Xử lý notification"""
        try:
            # Lưu vào history
            self.notifications.append(notification)
            
            # Gửi qua các channels
            for channel_type, channel in self.channels.items():
                try:
                    channel.send(notification)
                    self.notification_stats['by_channel'][channel_type.value] += 1
                except Exception as e:
                    print(f"[NOTIFY] ❌ Error sending to {channel_type.value}: {str(e)}")
            
            # Cập nhật stats
            self.notification_stats['total_sent'] += 1
            self.notification_stats['by_level'][notification['level']] += 1
            
            # Notify subscribers
            self.notify_subscribers(notification)
            
        except Exception as e:
            print(f"[NOTIFY] ❌ Error processing notification: {str(e)}")

    def notify_subscribers(self, notification):
        """Thông báo cho subscribers"""
        level = notification['level']
        for subscriber_level, callbacks in self.subscribers.items():
            if self.should_notify_subscriber(level, subscriber_level):
                for callback in callbacks:
                    try:
                        callback(notification)
                    except Exception as e:
                        print(f"[NOTIFY] ❌ Subscriber callback error: {str(e)}")

    def should_notify_subscriber(self, notification_level, subscriber_level):
        """Kiểm tra có nên notify subscriber không"""
        level_priority = {"info": 0, "warning": 1, "error": 2, "critical": 3}
        return level_priority[notification_level] >= level_priority[subscriber_level]

    def subscribe(self, callback, level=NotificationLevel.INFO):
        """Subscribe để nhận notifications"""
        if level.value not in self.subscribers:
            self.subscribers[level.value] = []
        
        self.subscribers[level.value].append(callback)

    def unsubscribe(self, callback, level=NotificationLevel.INFO):
        """Unsubscribe notifications"""
        if level.value in self.subscribers:
            try:
                self.subscribers[level.value].remove(callback)
            except ValueError:
                pass

    def get_recent_notifications(self, hours=24, level=None):
        """Lấy notifications gần đây"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent = []
        for notification in self.notifications:
            notif_time = datetime.fromisoformat(notification['timestamp'])
            if notif_time > cutoff_time:
                if level is None or notification['level'] == level.value:
                    recent.append(notification)
        
        return recent

    def get_notification_stats(self):
        """Lấy thống kê notifications"""
        return {
            **self.notification_stats,
            'queue_size': len(self.notification_queue),
            'history_size': len(self.notifications),
            'active_channels': len(self.channels),
            'subscribers_count': sum(len(callbacks) for callbacks in self.subscribers.values())
        }

    def print_notification_summary(self):
        """In tóm tắt notifications"""
        stats = self.get_notification_stats()
        
        print(f"\n[NOTIFY] 🔔 === NOTIFICATION SUMMARY ===")
        print(f"[NOTIFY] 📊 Total Sent: {stats['total_sent']}")
        print(f"[NOTIFY] 📋 Queue Size: {stats['queue_size']}")
        print(f"[NOTIFY] 📚 History Size: {stats['history_size']}")
        print(f"[NOTIFY] 📡 Active Channels: {stats['active_channels']}")
        
        print(f"[NOTIFY] 📈 By Level:")
        for level, count in stats['by_level'].items():
            if count > 0:
                print(f"[NOTIFY]   - {level.upper()}: {count}")
        
        print(f"[NOTIFY] 📤 By Channel:")
        for channel, count in stats['by_channel'].items():
            if count > 0:
                print(f"[NOTIFY]   - {channel.upper()}: {count}")
        
        print(f"[NOTIFY] =====================================\n")

    def stop(self):
        """Dừng notification system"""
        self.worker_active = False
        print("[NOTIFY] 🛑 Notification system stopped")


# Notification channel implementations
class ConsoleNotifier:
    def __init__(self, config):
        self.config = config
        self.colors = {
            'info': '\033[94m',      # Blue
            'warning': '\033[93m',   # Yellow
            'error': '\033[91m',     # Red
            'critical': '\033[95m',  # Magenta
            'reset': '\033[0m'       # Reset
        }

    def send(self, notification):
        """Gửi notification ra console"""
        level = notification['level']
        message = notification['message']
        context = notification['context']
        
        if self.config.get('show_timestamp', True):
            timestamp = datetime.fromisoformat(notification['timestamp']).strftime('%H:%M:%S')
            prefix = f"[{timestamp}]"
        else:
            prefix = ""
        
        if self.config.get('colored_output', True):
            color = self.colors.get(level, '')
            reset = self.colors['reset']
            level_str = f"{color}[{level.upper()}]{reset}"
        else:
            level_str = f"[{level.upper()}]"
        
        output = f"{prefix} {level_str} {message}"
        if context:
            output += f" ({context})"
        
        print(output)


class FileNotifier:
    def __init__(self, config):
        self.config = config
        self.log_file = config['log_file']
        
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def send(self, notification):
        """Gửi notification vào file"""
        try:
            log_entry = {
                'timestamp': notification['timestamp'],
                'level': notification['level'],
                'message': notification['message'],
                'context': notification['context'],
                'metadata': notification.get('metadata', {})
            }
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
            # Kiểm tra kích thước file
            self.rotate_log_if_needed()
            
        except Exception as e:
            print(f"[NOTIFY] ❌ File notification error: {str(e)}")

    def rotate_log_if_needed(self):
        """Rotate log file nếu quá lớn"""
        try:
            max_size = self.config.get('max_file_size_mb', 10) * 1024 * 1024
            
            if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > max_size:
                # Backup current log
                backup_file = f"{self.log_file}.backup"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(self.log_file, backup_file)
                
                print(f"[NOTIFY] 🔄 Log file rotated: {self.log_file}")
        except Exception as e:
            print(f"[NOTIFY] ❌ Log rotation error: {str(e)}")


class EmailNotifier:
    def __init__(self, config):
        self.config = config

    def send(self, notification):
        """Gửi notification qua email"""
        try:
            if not self.config.get('to_emails'):
                return
            
            # Tạo email
            msg = MIMEMultipart()
            msg['From'] = self.config['from_email']
            msg['To'] = ', '.join(self.config['to_emails'])
            msg['Subject'] = f"[{notification['level'].upper()}] InstaChatBot Notification"
            
            # Email body
            body = f"""
Notification Details:
- Level: {notification['level'].upper()}
- Time: {notification['timestamp']}
- Message: {notification['message']}
- Context: {notification['context']}
- Metadata: {json.dumps(notification.get('metadata', {}), indent=2)}
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Gửi email
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.starttls()
            server.login(self.config['username'], self.config['password'])
            
            text = msg.as_string()
            server.sendmail(self.config['from_email'], self.config['to_emails'], text)
            server.quit()
            
        except Exception as e:
            print(f"[NOTIFY] ❌ Email notification error: {str(e)}")


class WebhookNotifier:
    def __init__(self, config):
        self.config = config

    def send(self, notification):
        """Gửi notification qua webhook"""
        try:
            import requests
            
            payload = {
                'notification': notification,
                'timestamp': notification['timestamp'],
                'source': 'InstaChatBot'
            }
            
            headers = self.config.get('headers', {})
            headers['Content-Type'] = 'application/json'
            
            response = requests.post(
                self.config['url'],
                json=payload,
                headers=headers,
                timeout=10
            )
            
            response.raise_for_status()
            
        except Exception as e:
            print(f"[NOTIFY] ❌ Webhook notification error: {str(e)}")


# Singleton instance
_notification_system = None

def get_notification_system():
    """Lấy instance singleton của NotificationSystem"""
    global _notification_system
    if _notification_system is None:
        _notification_system = NotificationSystem()
    return _notification_system


# Convenience functions
def notify_info(message, context="", metadata=None):
    """Gửi info notification"""
    get_notification_system().send_notification(message, NotificationLevel.INFO, context, metadata)

def notify_warning(message, context="", metadata=None):
    """Gửi warning notification"""
    get_notification_system().send_notification(message, NotificationLevel.WARNING, context, metadata)

def notify_error(message, context="", metadata=None):
    """Gửi error notification"""
    get_notification_system().send_notification(message, NotificationLevel.ERROR, context, metadata)

def notify_critical(message, context="", metadata=None):
    """Gửi critical notification"""
    get_notification_system().send_notification(message, NotificationLevel.CRITICAL, context, metadata)


if __name__ == "__main__":
    # Test notification system
    notif_system = get_notification_system()
    
    # Test different levels
    notify_info("Bot started successfully", "startup")
    notify_warning("High memory usage detected", "performance")
    notify_error("Failed to connect to Instagram", "connection")
    notify_critical("System crash detected", "system")
    
    # Test subscriber
    def custom_handler(notification):
        print(f"Custom handler: {notification['message']}")
    
    notif_system.subscribe(custom_handler, NotificationLevel.WARNING)
    
    # Send more notifications
    notify_warning("Another warning", "test")
    
    # Print summary
    time.sleep(1)  # Wait for processing
    notif_system.print_notification_summary()
    
    # Stop system
    notif_system.stop() 