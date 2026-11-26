import os

from utils.cache_manager import CacheManager, ResponseCache
from utils.notification_system import NotificationLevel, NotificationSystem


def test_cache_manager_json_disk_promotion_without_keyerror(tmp_path):
    cache = CacheManager(cache_dir=str(tmp_path / "cache"), persist_threshold_bytes=10)
    payload = {"greeting": "xin chào", "items": list(range(20))}
    cache.set("k1", payload, ttl_seconds=600)

    # Xóa khỏi memory cache để ép đọc lại từ đĩa JSON
    cache.memory_cache.clear()
    loaded = cache.get("k1")
    assert loaded == payload
    assert "k1" in cache.memory_cache
    assert "ttl" in cache.memory_cache["k1"]

    # Đảm bảo file lưu trên đĩa là JSON, không phải pickle nhị phân
    disk_files = [f for f in os.listdir(tmp_path / "cache") if f.endswith(".json")]
    assert disk_files


def test_response_cache_isolates_users_by_default(tmp_path):
    rc = ResponseCache(cache_dir=str(tmp_path / "resp_cache"))
    rc.cache_response("hôm nay bạn ăn gì chưa", "mình ăn phở rồi", user_id="alice")

    assert rc.get_cached_response("hôm nay bạn ăn gì chưa", user_id="alice") == "mình ăn phở rồi"
    assert rc.get_cached_response("hôm nay bạn ăn gì chưa", user_id="bob") is None
    assert rc.get_cached_response("bạn ăn cơm chưa vậy", user_id="alice") is None


def test_notification_system_critical_delivered_once(tmp_path):
    cfg_file = tmp_path / "notif_cfg.json"
    cfg_file.write_text(
        '{"console":{"enabled":false},"file":{"enabled":true,"log_file":"'
        + str((tmp_path / "notif.log")).replace("\\", "/")
        + '","max_file_size_mb":5},"email":{"enabled":false},"webhook":{"enabled":false},'
        '"filters":{"min_level":"info","keywords_filter":[],"rate_limit_per_minute":60}}',
        encoding="utf-8",
    )
    ns = NotificationSystem(config_file=str(cfg_file))
    received = []
    ns.subscribe(lambda n: received.append(n), NotificationLevel.CRITICAL)

    try:
        ns.send_notification("Checkpoint detected!", NotificationLevel.CRITICAL, "safety")
        assert len(received) == 1
        assert ns.get_notification_stats()["total_sent"] == 1
        assert ns.get_notification_stats()["queue_size"] == 0
    finally:
        ns.stop()
