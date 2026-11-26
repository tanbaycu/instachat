from collections import OrderedDict
from datetime import datetime
import hashlib
import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from config.config_manager import get_data_dir


class CacheManager:
    """LRU cache kết hợp lưu đĩa bằng JSON an toàn (loại bỏ hoàn toàn pickle)."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_memory_items: int = 1000,
        max_file_size_mb: int = 100,
        persist_threshold_bytes: int = 512,
    ):
        self.cache_dir = cache_dir or get_data_dir("cache")
        self.max_memory_items = max_memory_items
        self.max_file_size_mb = max_file_size_mb
        self.persist_threshold_bytes = persist_threshold_bytes

        self.memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.cache_stats: Dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "memory_items": 0,
            "disk_items": 0,
            "total_size_mb": 0.0,
        }
        self.lock = threading.RLock()

        os.makedirs(self.cache_dir, exist_ok=True)
        self.load_cache_stats()

    def generate_cache_key(self, data: Any) -> str:
        if isinstance(data, dict):
            sorted_data = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            sorted_data = str(data)
        return hashlib.sha256(sorted_data.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            if key in self.memory_cache:
                item = self.memory_cache.pop(key)
                if self.is_expired(item):
                    self.cache_stats["memory_items"] = len(self.memory_cache)
                    self.cache_stats["misses"] += 1
                    return default
                item["access_count"] = item.get("access_count", 0) + 1
                self.memory_cache[key] = item
                self.cache_stats["hits"] += 1
                return item["data"]

            disk_item = self._read_disk_item(key)
            if disk_item is not None:
                # Đưa đầy đủ metadata {data, timestamp, ttl, access_count} vào RAM để tránh KeyError 'ttl'.
                self.set_memory_cache(key, disk_item)
                self.cache_stats["hits"] += 1
                return disk_item["data"]

            self.cache_stats["misses"] += 1
            return default

    def set(self, key: str, value: Any, ttl_seconds: int = 3600, persist: Optional[bool] = None) -> None:
        with self.lock:
            cache_item: Dict[str, Any] = {
                "data": value,
                "timestamp": time.time(),
                "ttl": ttl_seconds,
                "access_count": 0,
            }
            self.set_memory_cache(key, cache_item)

            should_save = self.should_persist_to_disk(value) if persist is None else persist
            if should_save:
                self.set_disk_cache(key, cache_item)

    def set_memory_cache(self, key: str, cache_item: Dict[str, Any]) -> None:
        if key in self.memory_cache:
            del self.memory_cache[key]
        self.memory_cache[key] = cache_item

        while len(self.memory_cache) > self.max_memory_items:
            oldest_key = next(iter(self.memory_cache))
            del self.memory_cache[oldest_key]

        self.cache_stats["memory_items"] = len(self.memory_cache)

    def should_persist_to_disk(self, value: Any) -> bool:
        try:
            serialized = json.dumps(value, ensure_ascii=False)
            return len(serialized.encode("utf-8")) > self.persist_threshold_bytes
        except (TypeError, ValueError):
            return False

    def _disk_path(self, key: str) -> str:
        safe_key = "".join(c for c in key if c.isalnum() or c in "-_")
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def set_disk_cache(self, key: str, cache_item: Dict[str, Any]) -> None:
        """Ghi nguyên tử (atomic write) ra file JSON để tránh hỏng file khi tắt đột ngột."""
        cache_file = self._disk_path(key)
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix=".cache_", suffix=".tmp", dir=self.cache_dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(cache_item, f, ensure_ascii=False)
                os.replace(tmp_path, cache_file)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            self.update_cache_size()
        except Exception as exc:
            print(f"[CACHE] ⚠️ Lỗi lưu disk cache: {exc}")

    def _read_disk_item(self, key: str) -> Optional[Dict[str, Any]]:
        cache_file = self._disk_path(key)
        if not os.path.exists(cache_file):
            return None
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_item = json.load(f)

            if not isinstance(cache_item, dict) or "data" not in cache_item:
                os.remove(cache_file)
                return None

            cache_item.setdefault("timestamp", time.time())
            cache_item.setdefault("ttl", 3600)
            cache_item.setdefault("access_count", 0)

            if self.is_expired(cache_item):
                os.remove(cache_file)
                self.update_cache_size()
                return None

            cache_item["access_count"] += 1
            return cache_item
        except Exception:
            try:
                os.remove(cache_file)
            except OSError:
                pass
            return None

    def get_from_disk(self, key: str) -> Any:
        item = self._read_disk_item(key)
        return item["data"] if item is not None else None

    def is_expired(self, cache_item: Dict[str, Any]) -> bool:
        ttl = cache_item.get("ttl", 0)
        if ttl <= 0:
            return False
        return (time.time() - cache_item.get("timestamp", 0)) > ttl

    def delete(self, key: str) -> None:
        with self.lock:
            self.memory_cache.pop(key, None)
            cache_file = self._disk_path(key)
            if os.path.exists(cache_file):
                os.remove(cache_file)
            self.cache_stats["memory_items"] = len(self.memory_cache)
            self.update_cache_size()

    def clear(self) -> None:
        with self.lock:
            self.memory_cache.clear()
            if os.path.exists(self.cache_dir):
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith(".json") and filename != "cache_stats.json":
                        os.remove(os.path.join(self.cache_dir, filename))
            self.cache_stats = {
                "hits": 0,
                "misses": 0,
                "memory_items": 0,
                "disk_items": 0,
                "total_size_mb": 0.0,
            }

    def cleanup_expired(self) -> None:
        with self.lock:
            expired_keys = [k for k, v in self.memory_cache.items() if self.is_expired(v)]
            for key in expired_keys:
                del self.memory_cache[key]

            if os.path.exists(self.cache_dir):
                for filename in os.listdir(self.cache_dir):
                    if not filename.endswith(".json") or filename == "cache_stats.json":
                        continue
                    cache_file = os.path.join(self.cache_dir, filename)
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cache_item = json.load(f)
                        if not isinstance(cache_item, dict) or self.is_expired(cache_item):
                            os.remove(cache_file)
                    except Exception:
                        try:
                            os.remove(cache_file)
                        except OSError:
                            pass

            self.cache_stats["memory_items"] = len(self.memory_cache)
            self.update_cache_size()

    def update_cache_size(self) -> None:
        total_size = 0
        disk_items = 0
        if os.path.exists(self.cache_dir):
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(".json") and filename != "cache_stats.json":
                    file_path = os.path.join(self.cache_dir, filename)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
                        disk_items += 1
        self.cache_stats["total_size_mb"] = total_size / (1024 * 1024)
        self.cache_stats["disk_items"] = disk_items

    def get_cache_stats(self) -> Dict[str, Any]:
        with self.lock:
            total = self.cache_stats["hits"] + self.cache_stats["misses"]
            hit_rate = (self.cache_stats["hits"] / max(1, total)) * 100.0
            return {
                **self.cache_stats,
                "hit_rate_percent": hit_rate,
                "memory_usage_percent": (len(self.memory_cache) / max(1, self.max_memory_items)) * 100.0,
                "disk_usage_percent": (
                    self.cache_stats["total_size_mb"] / max(1, self.max_file_size_mb)
                ) * 100.0,
            }

    def save_cache_stats(self) -> None:
        try:
            stats_file = os.path.join(self.cache_dir, "cache_stats.json")
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(self.cache_stats, f, indent=2)
        except Exception:
            pass

    def load_cache_stats(self) -> None:
        try:
            stats_file = os.path.join(self.cache_dir, "cache_stats.json")
            if os.path.exists(stats_file):
                with open(stats_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.cache_stats.update(loaded)
        except Exception:
            pass

    def print_cache_summary(self) -> None:
        stats = self.get_cache_stats()
        print("\n[CACHE] 💾 === CACHE SUMMARY ===")
        print(f"[CACHE] 📊 Hit Rate: {stats['hit_rate_percent']:.1f}%")
        print(f"[CACHE] 🧠 Memory Items: {stats['memory_items']}/{self.max_memory_items}")
        print(f"[CACHE] 💽 Disk Items: {stats['disk_items']} ({stats['total_size_mb']:.2f} MB)")
        print("[CACHE] ===============================\n")


class ResponseCache(CacheManager):
    """Cache cho phản hồi AI; chỉ trả kết quả khớp chính xác (user_id, message) theo mặc định."""

    def __init__(self, cache_dir: Optional[str] = None):
        super().__init__(
            cache_dir=cache_dir or os.path.join(get_data_dir("cache"), "responses"),
            max_memory_items=500,
        )
        # Giới hạn từ khóa trong index để tránh rò rỉ bộ nhớ khi chạy 24/7
        self.response_patterns: OrderedDict[str, List[str]] = OrderedDict()
        self.max_pattern_keys = 500

    def cache_response(
        self, user_message: str, response: str, user_id: str = "default", ttl_seconds: int = 3600
    ) -> None:
        cache_key = self.generate_response_key(user_message, user_id)
        response_data = {
            "response": response,
            "user_message": user_message,
            "user_id": user_id,
            "cached_at": datetime.now().isoformat(),
        }
        self.set(cache_key, response_data, ttl_seconds)
        self.save_response_pattern(user_message, cache_key)

    def get_cached_response(
        self, user_message: str, user_id: str = "default", allow_fuzzy: bool = False
    ) -> Optional[str]:
        cache_key = self.generate_response_key(user_message, user_id)
        cached_data = self.get(cache_key)
        if cached_data and cached_data.get("user_id") == user_id:
            return cached_data.get("response")

        if allow_fuzzy:
            return self.find_similar_response(user_message, user_id)
        return None

    def generate_response_key(self, message: str, user_id: str) -> str:
        normalized = " ".join(message.lower().split())
        return self.generate_cache_key({"user_id": user_id, "message": normalized})

    def save_response_pattern(self, message: str, cache_key: str) -> None:
        words = {w for w in message.lower().split() if len(w) > 3}
        with self.lock:
            for word in words:
                keys = self.response_patterns.pop(word, [])
                if cache_key not in keys:
                    keys.append(cache_key)
                if len(keys) > 20:
                    keys = keys[-20:]
                self.response_patterns[word] = keys
                while len(self.response_patterns) > self.max_pattern_keys:
                    self.response_patterns.popitem(last=False)

    def find_similar_response(self, message: str, user_id: str) -> Optional[str]:
        """Tìm câu trả lời tương tự trong phạm vi đúng user_id và độ giống >= 0.8."""
        query_words = {w for w in message.lower().split() if len(w) > 2}
        if not query_words:
            return None

        candidate_keys: List[str] = []
        with self.lock:
            for word in query_words:
                if word in self.response_patterns:
                    candidate_keys.extend(self.response_patterns[word])

        best_response = None
        best_score = 0.0
        for candidate_key in set(candidate_keys):
            cached_data = self.get(candidate_key)
            if not cached_data or cached_data.get("user_id") != user_id:
                continue
            cached_words = {w for w in cached_data.get("user_message", "").lower().split() if len(w) > 2}
            if not cached_words:
                continue
            union = query_words | cached_words
            score = len(query_words & cached_words) / len(union) if union else 0.0
            if score >= 0.8 and score > best_score:
                best_score = score
                best_response = cached_data.get("response")

        return best_response


class ImageCache(CacheManager):
    """Cache kết quả tạo ảnh theo prompt mô tả."""

    def __init__(self, cache_dir: Optional[str] = None):
        super().__init__(
            cache_dir=cache_dir or os.path.join(get_data_dir("cache"), "images"),
            max_memory_items=100,
            max_file_size_mb=500,
            persist_threshold_bytes=0,
        )

    def cache_image(
        self,
        description: str,
        image_ref: str,
        ttl_seconds: int = 86400,
        is_file: bool = True,
    ) -> None:
        cache_key = self.generate_cache_key(" ".join(description.lower().split()))
        image_data = {
            "url": None if is_file else image_ref,
            "file_path": image_ref if is_file else None,
            "description": description,
            "cached_at": datetime.now().isoformat(),
        }
        self.set(cache_key, image_data, ttl_seconds, persist=True)

    def get_cached_image(self, description: str) -> Optional[Dict[str, Any]]:
        cache_key = self.generate_cache_key(" ".join(description.lower().split()))
        cached_data = self.get(cache_key)
        if not cached_data:
            return None
        file_path = cached_data.get("file_path")
        if file_path and not os.path.exists(file_path):
            self.delete(cache_key)
            return None
        return cached_data


_cache_manager: Optional[CacheManager] = None
_response_cache: Optional[ResponseCache] = None
_image_cache: Optional[ImageCache] = None
_cache_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    global _cache_manager
    with _cache_lock:
        if _cache_manager is None:
            _cache_manager = CacheManager()
        return _cache_manager


def get_response_cache() -> ResponseCache:
    global _response_cache
    with _cache_lock:
        if _response_cache is None:
            _response_cache = ResponseCache()
        return _response_cache


def get_image_cache() -> ImageCache:
    global _image_cache
    with _cache_lock:
        if _image_cache is None:
            _image_cache = ImageCache()
        return _image_cache


def reset_cache_managers() -> None:
    global _cache_manager, _response_cache, _image_cache
    with _cache_lock:
        _cache_manager = None
        _response_cache = None
        _image_cache = None


def cache_result(ttl_seconds: int = 3600, cache_key_func=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            if cache_key_func:
                cache_key = cache_key_func(*args, **kwargs)
            else:
                cache_key = cache_manager.generate_cache_key(f"{func.__name__}_{args}_{kwargs}")
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            return result

        return wrapper

    return decorator
