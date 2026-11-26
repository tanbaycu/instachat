from collections import deque
from datetime import datetime
from functools import wraps
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

import psutil

from config.config_manager import get_data_dir


class PerformanceMonitor:
    """Theo dõi CPU, RAM, response time và health score của bot theo thời gian thực."""

    def __init__(self, log_file: Optional[str] = None):
        logs_dir = get_data_dir("logs")
        self.log_file = log_file or os.path.join(logs_dir, "performance_logs.json")
        self.start_time = datetime.now()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self.metrics: Dict[str, Any] = {
            "cpu_usage": deque(maxlen=100),
            "memory_usage": deque(maxlen=100),
            "response_times": deque(maxlen=100),
            "message_count": 0,
            "error_count": 0,
            "avg_response_time": 0.0,
            "peak_memory": 0.0,
            "peak_cpu": 0.0,
        }

        self.monitoring_active = False
        self.monitor_thread: Optional[threading.Thread] = None

        os.makedirs(os.path.dirname(self.log_file) or logs_dir, exist_ok=True)

    def start_monitoring(self, interval: float = 10.0) -> None:
        """Khởi chạy thread nền thu thập CPU/RAM; có thể dừng tức thì qua stop_event."""
        with self._lock:
            if self.monitoring_active:
                return
            self._stop_event.clear()
            self.monitoring_active = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop, args=(interval,), daemon=True
            )
            self.monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Dừng thread giám sát ngay lập tức không bị block bởi sleep dài."""
        with self._lock:
            self.monitoring_active = False
            self._stop_event.set()
            thread = self.monitor_thread
            self.monitor_thread = None

        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _monitor_loop(self, interval: float) -> None:
        # Gọi lần đầu để khởi tạo baseline CPU của psutil
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

        while not self._stop_event.is_set():
            try:
                cpu_percent = float(psutil.cpu_percent(interval=0.1))
                memory_percent = float(psutil.virtual_memory().percent)

                with self._lock:
                    self.metrics["cpu_usage"].append(cpu_percent)
                    self.metrics["memory_usage"].append(memory_percent)
                    self.metrics["peak_cpu"] = max(self.metrics["peak_cpu"], cpu_percent)
                    self.metrics["peak_memory"] = max(self.metrics["peak_memory"], memory_percent)
            except Exception as exc:
                print(f"[MONITOR] ❌ Lỗi monitoring: {exc}")

            if self._stop_event.wait(timeout=max(0.2, float(interval))):
                break

    def record_response_time(self, response_time: float) -> None:
        with self._lock:
            self.metrics["response_times"].append(float(response_time))
            self.metrics["message_count"] += 1
            times = self.metrics["response_times"]
            self.metrics["avg_response_time"] = sum(times) / len(times) if times else 0.0

    def record_error(self) -> None:
        with self._lock:
            self.metrics["error_count"] += 1

    def get_current_stats(self) -> Dict[str, Any]:
        with self._lock:
            uptime = datetime.now() - self.start_time
            cpu_list = list(self.metrics["cpu_usage"])
            mem_list = list(self.metrics["memory_usage"])
            msg_count = self.metrics["message_count"]
            err_count = self.metrics["error_count"]

            return {
                "uptime_seconds": uptime.total_seconds(),
                "uptime_formatted": str(uptime).split(".")[0],
                "current_cpu": cpu_list[-1] if cpu_list else 0.0,
                "current_memory": mem_list[-1] if mem_list else 0.0,
                "avg_cpu": sum(cpu_list) / len(cpu_list) if cpu_list else 0.0,
                "avg_memory": sum(mem_list) / len(mem_list) if mem_list else 0.0,
                "peak_cpu": self.metrics["peak_cpu"],
                "peak_memory": self.metrics["peak_memory"],
                "total_messages": msg_count,
                "total_errors": err_count,
                "avg_response_time": self.metrics["avg_response_time"],
                "error_rate": (err_count / max(1, msg_count)) * 100.0,
            }

    def get_health_status(self) -> Dict[str, Any]:
        stats = self.get_current_stats()
        health_score = 100
        issues: List[str] = []

        if stats["avg_cpu"] > 80:
            health_score -= 30
            issues.append("CPU usage cao")
        elif stats["avg_cpu"] > 60:
            health_score -= 15
            issues.append("CPU usage trung bình")

        if stats["avg_memory"] > 85:
            health_score -= 30
            issues.append("Memory usage cao")
        elif stats["avg_memory"] > 65:
            health_score -= 15
            issues.append("Memory usage trung bình")

        if stats["avg_response_time"] > 10:
            health_score -= 25
            issues.append("Response time chậm")
        elif stats["avg_response_time"] > 5:
            health_score -= 10
            issues.append("Response time trung bình")

        if stats["error_rate"] > 10:
            health_score -= 20
            issues.append("Error rate cao")
        elif stats["error_rate"] > 5:
            health_score -= 10
            issues.append("Error rate trung bình")

        score = max(0, health_score)
        if score >= 90:
            status = "EXCELLENT"
        elif score >= 75:
            status = "GOOD"
        elif score >= 60:
            status = "FAIR"
        elif score >= 40:
            status = "POOR"
        else:
            status = "CRITICAL"

        return {
            "status": status,
            "score": score,
            "issues": issues,
            "recommendations": self._get_recommendations(issues),
        }

    def get_health_score(self) -> float:
        """Trả về điểm sức khỏe chuẩn hóa trong đoạn [0.0, 1.0]."""
        return self.get_health_status()["score"] / 100.0

    def _get_recommendations(self, issues: List[str]) -> List[str]:
        recommendations: List[str] = []
        if "CPU usage cao" in issues:
            recommendations.append("Giảm tần suất polling hoặc bật chế độ idle")
        if "Memory usage cao" in issues:
            recommendations.append("Dọn dẹp cache và khởi động lại trình duyệt định kỳ")
        if "Response time chậm" in issues:
            recommendations.append("Kiểm tra độ trễ mạng/proxy hoặc đổi model Flash nhẹ hơn")
        if "Error rate cao" in issues:
            recommendations.append("Kiểm tra log lỗi và trạng thái tài khoản Instagram")
        return recommendations

    def save_report(self) -> bool:
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "stats": self.get_current_stats(),
                "health": self.get_health_status(),
            }
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            print(f"[MONITOR] ❌ Lỗi lưu báo cáo: {exc}")
            return False

    def print_summary(self) -> None:
        stats = self.get_current_stats()
        health = self.get_health_status()
        print("\n[MONITOR] 📊 === PERFORMANCE SUMMARY ===")
        print(f"[MONITOR] ⏱️ Uptime: {stats['uptime_formatted']}")
        print(
            f"[MONITOR] 💻 CPU: {stats['current_cpu']:.1f}% "
            f"(avg: {stats['avg_cpu']:.1f}%, peak: {stats['peak_cpu']:.1f}%)"
        )
        print(
            f"[MONITOR] 🧠 Memory: {stats['current_memory']:.1f}% "
            f"(avg: {stats['avg_memory']:.1f}%, peak: {stats['peak_memory']:.1f}%)"
        )
        print(
            f"[MONITOR] 💬 Messages: {stats['total_messages']} "
            f"(avg response: {stats['avg_response_time']:.2f}s)"
        )
        print(f"[MONITOR] ❌ Errors: {stats['total_errors']} (rate: {stats['error_rate']:.1f}%)")
        print(f"[MONITOR] 🏥 Health: {health['status']} ({health['score']}/100)")
        print("[MONITOR] =====================================\n")


_performance_monitor: Optional[PerformanceMonitor] = None
_monitor_lock = threading.Lock()


def get_performance_monitor(log_file: Optional[str] = None) -> PerformanceMonitor:
    global _performance_monitor
    with _monitor_lock:
        if _performance_monitor is None:
            _performance_monitor = PerformanceMonitor(log_file=log_file)
        return _performance_monitor


def reset_performance_monitor() -> None:
    global _performance_monitor
    with _monitor_lock:
        if _performance_monitor is not None:
            _performance_monitor.stop_monitoring()
        _performance_monitor = None


def measure_response_time(func):
    """Decorator tự động đo thời gian xử lý của hàm và ghi nhận lỗi nếu có."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        monitor = get_performance_monitor()
        try:
            result = func(*args, **kwargs)
            monitor.record_response_time(time.time() - start_time)
            return result
        except Exception:
            monitor.record_error()
            raise

    return wrapper
