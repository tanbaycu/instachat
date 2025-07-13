import time
import traceback
import logging
from datetime import datetime
from functools import wraps
import json
import os
from enum import Enum


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorHandler:
    def __init__(self, log_file="monitoring/error_logs.json"):
        self.log_file = log_file
        self.error_counts = {}
        self.recent_errors = []
        self.max_recent_errors = 50
        
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('monitoring/error_handler.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        print("[ERROR] 🛡️ Error Handler đã khởi tạo")

    def log_error(self, error, context="", severity=ErrorSeverity.MEDIUM, user_message=""):
        """Ghi lại lỗi với thông tin chi tiết"""
        error_info = {
            'timestamp': datetime.now().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'severity': severity.value,
            'user_message': user_message,
            'traceback': traceback.format_exc()
        }
        
        # Đếm lỗi theo loại
        error_type = error_info['error_type']
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Thêm vào recent errors
        self.recent_errors.append(error_info)
        if len(self.recent_errors) > self.max_recent_errors:
            self.recent_errors.pop(0)
        
        # Log theo severity
        if severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"CRITICAL ERROR in {context}: {str(error)}")
        elif severity == ErrorSeverity.HIGH:
            self.logger.error(f"HIGH ERROR in {context}: {str(error)}")
        elif severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"MEDIUM ERROR in {context}: {str(error)}")
        else:
            self.logger.info(f"LOW ERROR in {context}: {str(error)}")
        
        # Lưu vào file
        self.save_error_log(error_info)
        
        return error_info

    def save_error_log(self, error_info):
        """Lưu lỗi vào file"""
        try:
            # Đọc logs hiện tại
            logs = []
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            
            # Thêm error mới
            logs.append(error_info)
            
            # Giữ chỉ 1000 logs gần nhất
            if len(logs) > 1000:
                logs = logs[-1000:]
            
            # Lưu lại
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Không thể lưu error log: {str(e)}")

    def get_error_stats(self):
        """Lấy thống kê lỗi"""
        total_errors = sum(self.error_counts.values())
        
        # Phân loại theo severity
        severity_counts = {severity.value: 0 for severity in ErrorSeverity}
        for error in self.recent_errors:
            severity_counts[error['severity']] += 1
        
        return {
            'total_errors': total_errors,
            'error_types': self.error_counts,
            'severity_distribution': severity_counts,
            'recent_errors_count': len(self.recent_errors),
            'most_common_error': max(self.error_counts.items(), key=lambda x: x[1]) if self.error_counts else None
        }

    def get_recovery_suggestion(self, error_type):
        """Đề xuất cách khôi phục dựa trên loại lỗi"""
        suggestions = {
            'ConnectionError': [
                "Kiểm tra kết nối internet",
                "Thử lại sau 5-10 giây",
                "Restart Chrome driver"
            ],
            'TimeoutException': [
                "Tăng timeout duration",
                "Kiểm tra tốc độ internet",
                "Refresh trang web"
            ],
            'NoSuchElementException': [
                "Instagram có thể đã thay đổi giao diện",
                "Cập nhật selectors",
                "Kiểm tra page load"
            ],
            'StaleElementReferenceException': [
                "Tìm lại element",
                "Refresh page",
                "Thêm delay trước khi tương tác"
            ],
            'WebDriverException': [
                "Restart Chrome driver",
                "Kiểm tra Chrome version",
                "Clear Chrome cache"
            ],
            'APIError': [
                "Kiểm tra API key",
                "Kiểm tra quota API",
                "Thử lại với exponential backoff"
            ],
            'MemoryError': [
                "Dọn dẹp memory",
                "Giảm buffer size",
                "Restart application"
            ]
        }
        
        return suggestions.get(error_type, ["Khởi động lại ứng dụng", "Kiểm tra logs chi tiết"])

    def should_retry(self, error_type, attempt_count, max_attempts=3):
        """Quyết định có nên retry không"""
        # Các lỗi không nên retry
        no_retry_errors = [
            'KeyboardInterrupt',
            'SystemExit',
            'MemoryError',
            'SyntaxError',
            'IndentationError'
        ]
        
        if error_type in no_retry_errors:
            return False
        
        if attempt_count >= max_attempts:
            return False
        
        return True

    def get_retry_delay(self, attempt_count):
        """Tính delay cho retry (exponential backoff)"""
        base_delay = 1
        return min(base_delay * (2 ** attempt_count), 30)  # Max 30 seconds

    def print_error_summary(self):
        """In tóm tắt lỗi"""
        stats = self.get_error_stats()
        
        print(f"\n[ERROR] 🛡️ === ERROR SUMMARY ===")
        print(f"[ERROR] 📊 Total Errors: {stats['total_errors']}")
        
        if stats['most_common_error']:
            error_type, count = stats['most_common_error']
            print(f"[ERROR] 🔥 Most Common: {error_type} ({count} times)")
        
        print(f"[ERROR] 📈 Severity Distribution:")
        for severity, count in stats['severity_distribution'].items():
            if count > 0:
                print(f"[ERROR]   - {severity.upper()}: {count}")
        
        print(f"[ERROR] 🔍 Recent Errors: {stats['recent_errors_count']}")
        
        if self.recent_errors:
            print(f"[ERROR] 📋 Last 5 Errors:")
            for error in self.recent_errors[-5:]:
                print(f"[ERROR]   - {error['timestamp'][:19]} | {error['error_type']}: {error['error_message'][:50]}...")
        
        print(f"[ERROR] ================================\n")


# Singleton instance
_error_handler = None

def get_error_handler():
    """Lấy instance singleton của ErrorHandler"""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler


# Decorator cho retry logic
def retry_on_error(max_attempts=3, delay=1, exceptions=(Exception,)):
    """Decorator để retry function khi gặp lỗi"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            error_handler = get_error_handler()
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    error_type = type(e).__name__
                    
                    # Log error
                    error_handler.log_error(
                        e, 
                        context=f"{func.__name__} (attempt {attempt + 1}/{max_attempts})",
                        severity=ErrorSeverity.MEDIUM if attempt < max_attempts - 1 else ErrorSeverity.HIGH
                    )
                    
                    # Kiểm tra có nên retry không
                    if not error_handler.should_retry(error_type, attempt, max_attempts):
                        raise e
                    
                    if attempt < max_attempts - 1:
                        retry_delay = error_handler.get_retry_delay(attempt)
                        print(f"[ERROR] 🔄 Retry {attempt + 1}/{max_attempts} sau {retry_delay}s...")
                        time.sleep(retry_delay)
                    else:
                        # Lần thử cuối cùng thất bại
                        print(f"[ERROR] ❌ Tất cả {max_attempts} lần thử đều thất bại")
                        suggestions = error_handler.get_recovery_suggestion(error_type)
                        print(f"[ERROR] 💡 Suggestions: {', '.join(suggestions)}")
                        raise e
            
            return None
        return wrapper
    return decorator


# Decorator cho error logging
def log_errors(severity=ErrorSeverity.MEDIUM, context=""):
    """Decorator để tự động log errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                error_handler.log_error(
                    e, 
                    context=context or func.__name__,
                    severity=severity
                )
                raise e
        return wrapper
    return decorator


# Context manager cho error handling
class ErrorContext:
    def __init__(self, context="", severity=ErrorSeverity.MEDIUM):
        self.context = context
        self.severity = severity
        self.error_handler = get_error_handler()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error_handler.log_error(
                exc_val,
                context=self.context,
                severity=self.severity
            )
        return False  # Don't suppress the exception


if __name__ == "__main__":
    # Test error handler
    handler = get_error_handler()
    
    # Test error logging
    try:
        raise ValueError("Test error")
    except Exception as e:
        handler.log_error(e, context="Test context", severity=ErrorSeverity.HIGH)
    
    # Test retry decorator
    @retry_on_error(max_attempts=3)
    def failing_function():
        raise ConnectionError("Connection failed")
    
    try:
        failing_function()
    except:
        pass
    
    handler.print_error_summary() 