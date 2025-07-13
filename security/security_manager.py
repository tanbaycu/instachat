import time
import hashlib
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re


class SecurityManager:
    def __init__(self, config_file="security/security_config.json"):
        self.config_file = config_file
        self.message_history = deque(maxlen=1000)
        self.rate_limits = defaultdict(list)
        self.spam_scores = defaultdict(float)
        self.blocked_users = set()
        self.suspicious_patterns = []
        
        # Load config
        self.config = self.load_config()
        
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        print("[SECURITY] 🔐 Security Manager đã khởi tạo")

    def load_config(self):
        """Load security configuration"""
        default_config = {
            "rate_limits": {
                "messages_per_minute": 30,
                "messages_per_hour": 200,
                "ai_requests_per_minute": 10,
                "image_requests_per_hour": 20
            },
            "spam_detection": {
                "max_duplicate_messages": 3,
                "max_similar_messages": 5,
                "spam_keywords": ["spam", "bot", "fake", "scam", "hack"],
                "suspicious_patterns": [
                    r"\b(click|visit|go to)\s+https?://",
                    r"\b(free|win|prize|money)\b.*\b(click|visit|link)\b",
                    r"\b(urgent|limited time|act now)\b"
                ]
            },
            "account_protection": {
                "max_login_attempts": 3,
                "cooldown_minutes": 30,
                "suspicious_activity_threshold": 10
            },
            "content_filter": {
                "blocked_keywords": ["hate", "violence", "illegal"],
                "max_message_length": 1000,
                "allow_links": False
            }
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # Merge với default config
                return {**default_config, **config}
            else:
                # Tạo file config mặc định
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                return default_config
        except Exception as e:
            print(f"[SECURITY] ⚠️ Lỗi load config: {str(e)}")
            return default_config

    def check_rate_limit(self, user_id, action_type="message"):
        """Kiểm tra rate limit cho user"""
        current_time = time.time()
        
        # Lấy rate limit config
        if action_type == "message":
            per_minute = self.config["rate_limits"]["messages_per_minute"]
            per_hour = self.config["rate_limits"]["messages_per_hour"]
        elif action_type == "ai_request":
            per_minute = self.config["rate_limits"]["ai_requests_per_minute"]
            per_hour = self.config["rate_limits"]["ai_requests_per_minute"] * 6  # Approximate
        elif action_type == "image_request":
            per_minute = 2  # Stricter for images
            per_hour = self.config["rate_limits"]["image_requests_per_hour"]
        else:
            per_minute = 10
            per_hour = 100
        
        # Dọn dẹp old entries
        user_actions = self.rate_limits[user_id]
        cutoff_time = current_time - 3600  # 1 hour ago
        self.rate_limits[user_id] = [t for t in user_actions if t > cutoff_time]
        
        # Kiểm tra limits
        recent_actions = [t for t in self.rate_limits[user_id] if t > current_time - 60]  # Last minute
        hourly_actions = self.rate_limits[user_id]  # Last hour
        
        if len(recent_actions) >= per_minute:
            print(f"[SECURITY] 🚫 Rate limit exceeded (per minute): {user_id}")
            return False, f"Quá nhiều {action_type} trong 1 phút. Vui lòng chờ."
        
        if len(hourly_actions) >= per_hour:
            print(f"[SECURITY] 🚫 Rate limit exceeded (per hour): {user_id}")
            return False, f"Quá nhiều {action_type} trong 1 giờ. Vui lòng chờ."
        
        # Thêm action hiện tại
        self.rate_limits[user_id].append(current_time)
        return True, ""

    def detect_spam(self, message, user_id):
        """Phát hiện spam trong tin nhắn"""
        spam_score = 0
        reasons = []
        
        # 1. Kiểm tra duplicate messages
        user_messages = [msg for msg in self.message_history if msg.get('user_id') == user_id]
        recent_messages = [msg['content'] for msg in user_messages[-10:]]  # 10 tin nhắn gần nhất
        
        duplicate_count = recent_messages.count(message)
        if duplicate_count > self.config["spam_detection"]["max_duplicate_messages"]:
            spam_score += 30
            reasons.append("Tin nhắn trùng lặp")
        
        # 2. Kiểm tra similar messages
        similar_count = sum(1 for msg in recent_messages if self.similarity(message, msg) > 0.8)
        if similar_count > self.config["spam_detection"]["max_similar_messages"]:
            spam_score += 20
            reasons.append("Tin nhắn tương tự")
        
        # 3. Kiểm tra spam keywords
        spam_keywords = self.config["spam_detection"]["spam_keywords"]
        keyword_matches = sum(1 for keyword in spam_keywords if keyword.lower() in message.lower())
        if keyword_matches > 0:
            spam_score += keyword_matches * 10
            reasons.append("Chứa từ khóa spam")
        
        # 4. Kiểm tra suspicious patterns
        pattern_matches = 0
        for pattern in self.config["spam_detection"]["suspicious_patterns"]:
            if re.search(pattern, message, re.IGNORECASE):
                pattern_matches += 1
        
        if pattern_matches > 0:
            spam_score += pattern_matches * 15
            reasons.append("Pattern đáng nghi")
        
        # 5. Kiểm tra message length và structure
        if len(message) > self.config["content_filter"]["max_message_length"]:
            spam_score += 10
            reasons.append("Tin nhắn quá dài")
        
        # 6. Kiểm tra links nếu không được phép
        if not self.config["content_filter"]["allow_links"]:
            if re.search(r'https?://', message):
                spam_score += 25
                reasons.append("Chứa link")
        
        # 7. Kiểm tra CAPS LOCK
        if len(message) > 20 and message.isupper():
            spam_score += 15
            reasons.append("Toàn chữ hoa")
        
        # Cập nhật spam score cho user
        self.spam_scores[user_id] = (self.spam_scores[user_id] * 0.9) + (spam_score * 0.1)
        
        is_spam = spam_score > 50 or self.spam_scores[user_id] > 30
        
        if is_spam:
            print(f"[SECURITY] 🚨 Spam detected from {user_id}: {reasons}")
        
        return is_spam, spam_score, reasons

    def similarity(self, text1, text2):
        """Tính similarity giữa 2 text"""
        if not text1 or not text2:
            return 0
        
        # Simple similarity based on common words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0

    def check_content_filter(self, message):
        """Kiểm tra content filter"""
        blocked_keywords = self.config["content_filter"]["blocked_keywords"]
        
        for keyword in blocked_keywords:
            if keyword.lower() in message.lower():
                print(f"[SECURITY] 🚫 Blocked keyword detected: {keyword}")
                return False, f"Tin nhắn chứa nội dung không được phép"
        
        return True, ""

    def log_message(self, message, user_id, response="", action_taken=""):
        """Ghi lại tin nhắn vào history"""
        message_data = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'content': message,
            'response': response,
            'action_taken': action_taken,
            'spam_score': self.spam_scores.get(user_id, 0)
        }
        
        self.message_history.append(message_data)

    def is_user_blocked(self, user_id):
        """Kiểm tra user có bị block không"""
        return user_id in self.blocked_users

    def block_user(self, user_id, reason=""):
        """Block user"""
        self.blocked_users.add(user_id)
        print(f"[SECURITY] 🚫 User blocked: {user_id} - {reason}")

    def unblock_user(self, user_id):
        """Unblock user"""
        self.blocked_users.discard(user_id)
        print(f"[SECURITY] ✅ User unblocked: {user_id}")

    def validate_message(self, message, user_id):
        """Validation tổng hợp cho tin nhắn"""
        # Kiểm tra user có bị block không
        if self.is_user_blocked(user_id):
            return False, "User đã bị block"
        
        # Kiểm tra rate limit
        rate_ok, rate_msg = self.check_rate_limit(user_id, "message")
        if not rate_ok:
            return False, rate_msg
        
        # Kiểm tra content filter
        content_ok, content_msg = self.check_content_filter(message)
        if not content_ok:
            return False, content_msg
        
        # Kiểm tra spam
        is_spam, spam_score, reasons = self.detect_spam(message, user_id)
        if is_spam:
            # Auto-block nếu spam score quá cao
            if spam_score > 80:
                self.block_user(user_id, f"Spam score: {spam_score}")
                return False, "User đã bị block do spam"
            
            return False, f"Tin nhắn bị từ chối do spam (score: {spam_score})"
        
        return True, ""

    def get_security_stats(self):
        """Lấy thống kê bảo mật"""
        total_messages = len(self.message_history)
        spam_messages = sum(1 for msg in self.message_history if msg.get('spam_score', 0) > 30)
        
        return {
            'total_messages': total_messages,
            'spam_messages': spam_messages,
            'blocked_users': len(self.blocked_users),
            'active_rate_limits': len(self.rate_limits),
            'spam_rate': (spam_messages / max(1, total_messages)) * 100,
            'avg_spam_score': sum(self.spam_scores.values()) / max(1, len(self.spam_scores))
        }

    def print_security_summary(self):
        """In tóm tắt bảo mật"""
        stats = self.get_security_stats()
        
        print(f"\n[SECURITY] 🔐 === SECURITY SUMMARY ===")
        print(f"[SECURITY] 📊 Total Messages: {stats['total_messages']}")
        print(f"[SECURITY] 🚨 Spam Messages: {stats['spam_messages']} ({stats['spam_rate']:.1f}%)")
        print(f"[SECURITY] 🚫 Blocked Users: {stats['blocked_users']}")
        print(f"[SECURITY] ⏱️ Active Rate Limits: {stats['active_rate_limits']}")
        print(f"[SECURITY] 📈 Avg Spam Score: {stats['avg_spam_score']:.1f}")
        
        if self.blocked_users:
            print(f"[SECURITY] 🚫 Blocked Users List: {', '.join(list(self.blocked_users)[:5])}")
        
        print(f"[SECURITY] ===================================\n")

    def save_security_report(self, filename="security/security_report.json"):
        """Lưu báo cáo bảo mật"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'stats': self.get_security_stats(),
                'blocked_users': list(self.blocked_users),
                'recent_messages': list(self.message_history)[-50:],  # 50 tin nhắn gần nhất
                'config': self.config
            }
            
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"[SECURITY] 💾 Đã lưu báo cáo: {filename}")
            return True
            
        except Exception as e:
            print(f"[SECURITY] ❌ Lỗi lưu báo cáo: {str(e)}")
            return False


# Singleton instance
_security_manager = None

def get_security_manager():
    """Lấy instance singleton của SecurityManager"""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager


# Decorator cho security check
def security_check(func):
    """Decorator để kiểm tra bảo mật trước khi xử lý tin nhắn"""
    def wrapper(self, message, user_id="unknown", *args, **kwargs):
        security_manager = get_security_manager()
        
        # Validate message
        is_valid, error_msg = security_manager.validate_message(message, user_id)
        
        if not is_valid:
            print(f"[SECURITY] 🚫 Message rejected: {error_msg}")
            return error_msg
        
        # Log message
        try:
            result = func(self, message, user_id, *args, **kwargs)
            security_manager.log_message(message, user_id, str(result)[:100], "processed")
            return result
        except Exception as e:
            security_manager.log_message(message, user_id, "", f"error: {str(e)}")
            raise e
    
    return wrapper


if __name__ == "__main__":
    # Test security manager
    security = get_security_manager()
    
    # Test normal message
    print("Test 1: Normal message")
    valid, msg = security.validate_message("Hello, how are you?", "user1")
    print(f"Valid: {valid}, Message: {msg}")
    
    # Test spam
    print("\nTest 2: Spam message")
    valid, msg = security.validate_message("FREE MONEY CLICK HERE NOW!!!", "user2")
    print(f"Valid: {valid}, Message: {msg}")
    
    # Test rate limit
    print("\nTest 3: Rate limit")
    for i in range(35):  # Exceed rate limit
        valid, msg = security.validate_message(f"Message {i}", "user3")
        if not valid:
            print(f"Rate limited at message {i}: {msg}")
            break
    
    security.print_security_summary()
    security.save_security_report() 