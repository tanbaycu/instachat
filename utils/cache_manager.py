import json
import os
import time
import hashlib
import pickle
from datetime import datetime, timedelta
from collections import OrderedDict
import threading


class CacheManager:
    def __init__(self, cache_dir="utils/cache", max_memory_items=1000, max_file_size_mb=100):
        self.cache_dir = cache_dir
        self.max_memory_items = max_memory_items
        self.max_file_size_mb = max_file_size_mb
        
        # Memory cache (LRU)
        self.memory_cache = OrderedDict()
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'memory_items': 0,
            'disk_items': 0,
            'total_size_mb': 0
        }
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Tạo thư mục cache
        os.makedirs(cache_dir, exist_ok=True)
        
        # Load existing cache stats
        self.load_cache_stats()
        
        print("[CACHE] 💾 Cache Manager đã khởi tạo")

    def generate_cache_key(self, data):
        """Tạo cache key từ data"""
        if isinstance(data, dict):
            # Sắp xếp dict để key consistent
            sorted_data = json.dumps(data, sort_keys=True)
        else:
            sorted_data = str(data)
        
        return hashlib.md5(sorted_data.encode('utf-8')).hexdigest()

    def get(self, key, default=None):
        """Lấy item từ cache"""
        with self.lock:
            # Kiểm tra memory cache trước
            if key in self.memory_cache:
                # Move to end (LRU)
                value = self.memory_cache.pop(key)
                self.memory_cache[key] = value
                self.cache_stats['hits'] += 1
                
                # Kiểm tra expiry
                if self.is_expired(value):
                    del self.memory_cache[key]
                    self.cache_stats['misses'] += 1
                    return default
                
                return value['data']
            
            # Kiểm tra disk cache
            disk_value = self.get_from_disk(key)
            if disk_value is not None:
                # Load vào memory cache
                self.set_memory_cache(key, disk_value)
                self.cache_stats['hits'] += 1
                return disk_value
            
            self.cache_stats['misses'] += 1
            return default

    def set(self, key, value, ttl_seconds=3600):
        """Lưu item vào cache"""
        with self.lock:
            cache_item = {
                'data': value,
                'timestamp': time.time(),
                'ttl': ttl_seconds,
                'access_count': 0
            }
            
            # Lưu vào memory cache
            self.set_memory_cache(key, cache_item)
            
            # Lưu vào disk nếu item quan trọng hoặc lớn
            if self.should_persist_to_disk(value):
                self.set_disk_cache(key, cache_item)

    def set_memory_cache(self, key, cache_item):
        """Lưu vào memory cache với LRU eviction"""
        # Xóa item cũ nếu tồn tại
        if key in self.memory_cache:
            del self.memory_cache[key]
        
        # Thêm item mới
        self.memory_cache[key] = cache_item
        
        # LRU eviction
        while len(self.memory_cache) > self.max_memory_items:
            oldest_key = next(iter(self.memory_cache))
            del self.memory_cache[oldest_key]
        
        self.cache_stats['memory_items'] = len(self.memory_cache)

    def should_persist_to_disk(self, value):
        """Quyết định có nên lưu vào disk không"""
        # Lưu vào disk nếu:
        # 1. Dữ liệu lớn (>1KB)
        # 2. Dữ liệu có thể tái sử dụng nhiều lần
        
        try:
            size = len(json.dumps(value)) if isinstance(value, (dict, list)) else len(str(value))
            return size > 1024  # 1KB
        except:
            return False

    def set_disk_cache(self, key, cache_item):
        """Lưu vào disk cache"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{key}.cache")
            
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_item, f)
            
            self.cache_stats['disk_items'] += 1
            self.update_cache_size()
            
        except Exception as e:
            print(f"[CACHE] ⚠️ Lỗi lưu disk cache: {str(e)}")

    def get_from_disk(self, key):
        """Lấy từ disk cache"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{key}.cache")
            
            if not os.path.exists(cache_file):
                return None
            
            with open(cache_file, 'rb') as f:
                cache_item = pickle.load(f)
            
            # Kiểm tra expiry
            if self.is_expired(cache_item):
                os.remove(cache_file)
                return None
            
            # Cập nhật access count
            cache_item['access_count'] += 1
            
            return cache_item['data']
            
        except Exception as e:
            print(f"[CACHE] ⚠️ Lỗi đọc disk cache: {str(e)}")
            return None

    def is_expired(self, cache_item):
        """Kiểm tra item có hết hạn không"""
        if cache_item['ttl'] <= 0:  # No expiry
            return False
        
        return time.time() - cache_item['timestamp'] > cache_item['ttl']

    def delete(self, key):
        """Xóa item khỏi cache"""
        with self.lock:
            # Xóa từ memory
            if key in self.memory_cache:
                del self.memory_cache[key]
            
            # Xóa từ disk
            cache_file = os.path.join(self.cache_dir, f"{key}.cache")
            if os.path.exists(cache_file):
                os.remove(cache_file)

    def clear(self):
        """Xóa toàn bộ cache"""
        with self.lock:
            # Xóa memory cache
            self.memory_cache.clear()
            
            # Xóa disk cache
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.cache'):
                    os.remove(os.path.join(self.cache_dir, filename))
            
            # Reset stats
            self.cache_stats = {
                'hits': 0,
                'misses': 0,
                'memory_items': 0,
                'disk_items': 0,
                'total_size_mb': 0
            }

    def cleanup_expired(self):
        """Dọn dẹp items hết hạn"""
        with self.lock:
            # Cleanup memory cache
            expired_keys = []
            for key, item in self.memory_cache.items():
                if self.is_expired(item):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.memory_cache[key]
            
            # Cleanup disk cache
            disk_expired = 0
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.cache'):
                    try:
                        cache_file = os.path.join(self.cache_dir, filename)
                        with open(cache_file, 'rb') as f:
                            cache_item = pickle.load(f)
                        
                        if self.is_expired(cache_item):
                            os.remove(cache_file)
                            disk_expired += 1
                    except:
                        # Xóa file bị corrupt
                        os.remove(cache_file)
                        disk_expired += 1
            
            self.update_cache_size()
            
            print(f"[CACHE] 🧹 Cleaned up {len(expired_keys)} memory items, {disk_expired} disk items")

    def update_cache_size(self):
        """Cập nhật kích thước cache"""
        total_size = 0
        disk_items = 0
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.cache'):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
                    disk_items += 1
        
        self.cache_stats['total_size_mb'] = total_size / (1024 * 1024)
        self.cache_stats['disk_items'] = disk_items

    def get_cache_stats(self):
        """Lấy thống kê cache"""
        with self.lock:
            hit_rate = (self.cache_stats['hits'] / 
                       max(1, self.cache_stats['hits'] + self.cache_stats['misses'])) * 100
            
            return {
                **self.cache_stats,
                'hit_rate_percent': hit_rate,
                'memory_usage_percent': (len(self.memory_cache) / self.max_memory_items) * 100,
                'disk_usage_percent': (self.cache_stats['total_size_mb'] / self.max_file_size_mb) * 100
            }

    def save_cache_stats(self):
        """Lưu cache stats"""
        try:
            stats_file = os.path.join(self.cache_dir, 'cache_stats.json')
            with open(stats_file, 'w') as f:
                json.dump(self.cache_stats, f, indent=2)
        except Exception as e:
            print(f"[CACHE] ⚠️ Lỗi lưu cache stats: {str(e)}")

    def load_cache_stats(self):
        """Load cache stats"""
        try:
            stats_file = os.path.join(self.cache_dir, 'cache_stats.json')
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    self.cache_stats.update(json.load(f))
        except Exception as e:
            print(f"[CACHE] ⚠️ Lỗi load cache stats: {str(e)}")

    def print_cache_summary(self):
        """In tóm tắt cache"""
        stats = self.get_cache_stats()
        
        print(f"\n[CACHE] 💾 === CACHE SUMMARY ===")
        print(f"[CACHE] 📊 Hit Rate: {stats['hit_rate_percent']:.1f}%")
        print(f"[CACHE] 🧠 Memory Items: {stats['memory_items']}/{self.max_memory_items} ({stats['memory_usage_percent']:.1f}%)")
        print(f"[CACHE] 💽 Disk Items: {stats['disk_items']}")
        print(f"[CACHE] 📁 Disk Usage: {stats['total_size_mb']:.1f}MB/{self.max_file_size_mb}MB ({stats['disk_usage_percent']:.1f}%)")
        print(f"[CACHE] ✅ Hits: {stats['hits']}")
        print(f"[CACHE] ❌ Misses: {stats['misses']}")
        print(f"[CACHE] ===============================\n")


# Specialized cache classes
class ResponseCache(CacheManager):
    """Cache chuyên dụng cho AI responses"""
    
    def __init__(self):
        super().__init__(cache_dir="utils/cache/responses", max_memory_items=500)
        self.response_patterns = {}
    
    def cache_response(self, user_message, response, user_id="default", ttl_seconds=7200):
        """Cache AI response"""
        # Tạo key từ message và user context
        cache_key = self.generate_response_key(user_message, user_id)
        
        response_data = {
            'response': response,
            'user_message': user_message,
            'user_id': user_id,
            'cached_at': datetime.now().isoformat()
        }
        
        self.set(cache_key, response_data, ttl_seconds)
        
        # Lưu pattern để tìm similar responses
        self.save_response_pattern(user_message, cache_key)
    
    def get_cached_response(self, user_message, user_id="default"):
        """Lấy cached response"""
        cache_key = self.generate_response_key(user_message, user_id)
        cached_data = self.get(cache_key)
        
        if cached_data:
            return cached_data['response']
        
        # Tìm similar response
        return self.find_similar_response(user_message, user_id)
    
    def generate_response_key(self, message, user_id):
        """Tạo key cho response cache"""
        # Normalize message
        normalized = message.lower().strip()
        return self.generate_cache_key(f"{normalized}_{user_id}")
    
    def save_response_pattern(self, message, cache_key):
        """Lưu pattern để tìm similar responses"""
        words = set(message.lower().split())
        for word in words:
            if len(word) > 3:  # Chỉ lưu từ có ý nghĩa
                if word not in self.response_patterns:
                    self.response_patterns[word] = []
                self.response_patterns[word].append(cache_key)
    
    def find_similar_response(self, message, user_id):
        """Tìm response tương tự"""
        words = set(message.lower().split())
        candidate_keys = []
        
        for word in words:
            if word in self.response_patterns:
                candidate_keys.extend(self.response_patterns[word])
        
        # Tìm key xuất hiện nhiều nhất
        if candidate_keys:
            from collections import Counter
            most_common_key = Counter(candidate_keys).most_common(1)[0][0]
            cached_data = self.get(most_common_key)
            
            if cached_data:
                return cached_data['response']
        
        return None


class ImageCache(CacheManager):
    """Cache chuyên dụng cho images"""
    
    def __init__(self):
        super().__init__(cache_dir="utils/cache/images", max_memory_items=100, max_file_size_mb=500)
    
    def cache_image(self, description, image_url, ttl_seconds=86400):
        """Cache image URL"""
        cache_key = self.generate_cache_key(description.lower().strip())
        
        image_data = {
            'url': image_url,
            'description': description,
            'cached_at': datetime.now().isoformat()
        }
        
        self.set(cache_key, image_data, ttl_seconds)
    
    def get_cached_image(self, description):
        """Lấy cached image"""
        cache_key = self.generate_cache_key(description.lower().strip())
        cached_data = self.get(cache_key)
        
        if cached_data:
            return cached_data['url']
        
        return None


# Singleton instances
_cache_manager = None
_response_cache = None
_image_cache = None

def get_cache_manager():
    """Lấy instance singleton của CacheManager"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

def get_response_cache():
    """Lấy instance singleton của ResponseCache"""
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache

def get_image_cache():
    """Lấy instance singleton của ImageCache"""
    global _image_cache
    if _image_cache is None:
        _image_cache = ImageCache()
    return _image_cache


# Decorator cho caching
def cache_result(ttl_seconds=3600, cache_key_func=None):
    """Decorator để cache kết quả function"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            
            # Tạo cache key
            if cache_key_func:
                cache_key = cache_key_func(*args, **kwargs)
            else:
                cache_key = cache_manager.generate_cache_key(f"{func.__name__}_{args}_{kwargs}")
            
            # Kiểm tra cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Tính toán và cache
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            
            return result
        return wrapper
    return decorator


if __name__ == "__main__":
    # Test cache manager
    cache = get_cache_manager()
    
    # Test basic caching
    cache.set("test_key", "test_value", ttl_seconds=10)
    print(f"Cached value: {cache.get('test_key')}")
    
    # Test response cache
    response_cache = get_response_cache()
    response_cache.cache_response("Hello", "Hi there!", "user1")
    cached_response = response_cache.get_cached_response("Hello", "user1")
    print(f"Cached response: {cached_response}")
    
    # Test image cache
    image_cache = get_image_cache()
    image_cache.cache_image("sunset", "https://example.com/sunset.jpg")
    cached_image = image_cache.get_cached_image("sunset")
    print(f"Cached image: {cached_image}")
    
    # Print summaries
    cache.print_cache_summary()
    response_cache.print_cache_summary()
    image_cache.print_cache_summary()
    
    # Cleanup
    cache.cleanup_expired() 