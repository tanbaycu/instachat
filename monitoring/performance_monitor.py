import time
import psutil
import threading
from datetime import datetime, timedelta
import json
import os
from collections import deque


class PerformanceMonitor:
    def __init__(self, log_file="monitoring/performance_logs.json"):
        self.log_file = log_file
        self.start_time = datetime.now()
        self.metrics = {
            'cpu_usage': deque(maxlen=100),
            'memory_usage': deque(maxlen=100),
            'response_times': deque(maxlen=100),
            'message_count': 0,
            'error_count': 0,
            'avg_response_time': 0,
            'peak_memory': 0,
            'peak_cpu': 0
        }
        
        self.monitoring_active = False
        self.monitor_thread = None
        
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        print("[MONITOR] 📊 Performance Monitor đã khởi tạo")

    def start_monitoring(self, interval=5):
        """Bắt đầu theo dõi hiệu suất"""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        print(f"[MONITOR] 🚀 Bắt đầu theo dõi mỗi {interval}s")

    def stop_monitoring(self):
        """Dừng theo dõi hiệu suất"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join()
        print("[MONITOR] 🛑 Đã dừng theo dõi")

    def _monitor_loop(self, interval):
        """Vòng lặp theo dõi chính"""
        while self.monitoring_active:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                self.metrics['cpu_usage'].append(cpu_percent)
                
                # Memory usage
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                self.metrics['memory_usage'].append(memory_percent)
                
                # Cập nhật peak values
                self.metrics['peak_cpu'] = max(self.metrics['peak_cpu'], cpu_percent)
                self.metrics['peak_memory'] = max(self.metrics['peak_memory'], memory_percent)
                
                # Log nếu usage cao
                if cpu_percent > 80:
                    print(f"[MONITOR] ⚠️ CPU cao: {cpu_percent}%")
                if memory_percent > 80:
                    print(f"[MONITOR] ⚠️ Memory cao: {memory_percent}%")
                
                time.sleep(interval)
                
            except Exception as e:
                print(f"[MONITOR] ❌ Lỗi monitoring: {str(e)}")
                time.sleep(interval)

    def record_response_time(self, response_time):
        """Ghi lại thời gian phản hồi"""
        self.metrics['response_times'].append(response_time)
        self.metrics['message_count'] += 1
        
        # Tính average response time
        if self.metrics['response_times']:
            self.metrics['avg_response_time'] = sum(self.metrics['response_times']) / len(self.metrics['response_times'])
        
        # Cảnh báo nếu response time quá cao
        if response_time > 10:
            print(f"[MONITOR] ⚠️ Response time cao: {response_time:.2f}s")

    def record_error(self):
        """Ghi lại lỗi"""
        self.metrics['error_count'] += 1
        print(f"[MONITOR] ❌ Tổng lỗi: {self.metrics['error_count']}")

    def get_current_stats(self):
        """Lấy thống kê hiện tại"""
        uptime = datetime.now() - self.start_time
        
        return {
            'uptime_seconds': uptime.total_seconds(),
            'uptime_formatted': str(uptime).split('.')[0],
            'current_cpu': self.metrics['cpu_usage'][-1] if self.metrics['cpu_usage'] else 0,
            'current_memory': self.metrics['memory_usage'][-1] if self.metrics['memory_usage'] else 0,
            'avg_cpu': sum(self.metrics['cpu_usage']) / len(self.metrics['cpu_usage']) if self.metrics['cpu_usage'] else 0,
            'avg_memory': sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage']) if self.metrics['memory_usage'] else 0,
            'peak_cpu': self.metrics['peak_cpu'],
            'peak_memory': self.metrics['peak_memory'],
            'total_messages': self.metrics['message_count'],
            'total_errors': self.metrics['error_count'],
            'avg_response_time': self.metrics['avg_response_time'],
            'error_rate': (self.metrics['error_count'] / max(1, self.metrics['message_count'])) * 100
        }

    def get_health_status(self):
        """Đánh giá tình trạng sức khỏe hệ thống"""
        stats = self.get_current_stats()
        
        health_score = 100
        issues = []
        
        # Kiểm tra CPU
        if stats['avg_cpu'] > 80:
            health_score -= 30
            issues.append("CPU usage cao")
        elif stats['avg_cpu'] > 60:
            health_score -= 15
            issues.append("CPU usage trung bình")
        
        # Kiểm tra Memory
        if stats['avg_memory'] > 80:
            health_score -= 30
            issues.append("Memory usage cao")
        elif stats['avg_memory'] > 60:
            health_score -= 15
            issues.append("Memory usage trung bình")
        
        # Kiểm tra Response time
        if stats['avg_response_time'] > 10:
            health_score -= 25
            issues.append("Response time chậm")
        elif stats['avg_response_time'] > 5:
            health_score -= 10
            issues.append("Response time trung bình")
        
        # Kiểm tra Error rate
        if stats['error_rate'] > 10:
            health_score -= 20
            issues.append("Error rate cao")
        elif stats['error_rate'] > 5:
            health_score -= 10
            issues.append("Error rate trung bình")
        
        # Xác định status
        if health_score >= 90:
            status = "EXCELLENT"
        elif health_score >= 75:
            status = "GOOD"
        elif health_score >= 60:
            status = "FAIR"
        elif health_score >= 40:
            status = "POOR"
        else:
            status = "CRITICAL"
        
        return {
            'status': status,
            'score': max(0, health_score),
            'issues': issues,
            'recommendations': self._get_recommendations(issues)
        }

    def _get_recommendations(self, issues):
        """Đề xuất cải thiện dựa trên issues"""
        recommendations = []
        
        if "CPU usage cao" in issues:
            recommendations.append("Giảm tần suất polling, tối ưu thuật toán")
        if "Memory usage cao" in issues:
            recommendations.append("Dọn dẹp cache, giảm buffer size")
        if "Response time chậm" in issues:
            recommendations.append("Tối ưu AI prompt, cache responses")
        if "Error rate cao" in issues:
            recommendations.append("Kiểm tra network, cải thiện error handling")
        
        return recommendations

    def save_report(self):
        """Lưu báo cáo hiệu suất"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'stats': self.get_current_stats(),
                'health': self.get_health_status()
            }
            
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"[MONITOR] 💾 Đã lưu báo cáo: {self.log_file}")
            return True
            
        except Exception as e:
            print(f"[MONITOR] ❌ Lỗi lưu báo cáo: {str(e)}")
            return False

    def print_summary(self):
        """In tóm tắt hiệu suất"""
        stats = self.get_current_stats()
        health = self.get_health_status()
        
        print(f"\n[MONITOR] 📊 === PERFORMANCE SUMMARY ===")
        print(f"[MONITOR] ⏱️ Uptime: {stats['uptime_formatted']}")
        print(f"[MONITOR] 💻 CPU: {stats['current_cpu']:.1f}% (avg: {stats['avg_cpu']:.1f}%, peak: {stats['peak_cpu']:.1f}%)")
        print(f"[MONITOR] 🧠 Memory: {stats['current_memory']:.1f}% (avg: {stats['avg_memory']:.1f}%, peak: {stats['peak_memory']:.1f}%)")
        print(f"[MONITOR] 💬 Messages: {stats['total_messages']} (avg response: {stats['avg_response_time']:.2f}s)")
        print(f"[MONITOR] ❌ Errors: {stats['total_errors']} (rate: {stats['error_rate']:.1f}%)")
        print(f"[MONITOR] 🏥 Health: {health['status']} ({health['score']}/100)")
        
        if health['issues']:
            print(f"[MONITOR] ⚠️ Issues: {', '.join(health['issues'])}")
        
        if health['recommendations']:
            print(f"[MONITOR] 💡 Recommendations:")
            for rec in health['recommendations']:
                print(f"[MONITOR]   - {rec}")
        
        print(f"[MONITOR] =====================================\n")


# Singleton instance
_performance_monitor = None

def get_performance_monitor():
    """Lấy instance singleton của PerformanceMonitor"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


# Decorator để đo response time
def measure_response_time(func):
    """Decorator để đo thời gian phản hồi"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            response_time = time.time() - start_time
            get_performance_monitor().record_response_time(response_time)
            return result
        except Exception as e:
            get_performance_monitor().record_error()
            raise e
    return wrapper


if __name__ == "__main__":
    # Test performance monitor
    monitor = get_performance_monitor()
    monitor.start_monitoring(interval=2)
    
    try:
        # Simulate some work
        for i in range(5):
            time.sleep(1)
            monitor.record_response_time(0.5 + i * 0.1)
            if i == 3:
                monitor.record_error()
        
        monitor.print_summary()
        monitor.save_report()
        
    finally:
        monitor.stop_monitoring() 