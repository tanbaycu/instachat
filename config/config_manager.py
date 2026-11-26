import copy
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Hợp nhất đệ quy hai dict để giữ lại các khóa mặc định mới khi đọc file cũ."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: Optional[str], default: Optional[int]) -> Optional[int]:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_float(value: Optional[str], default: float) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def get_data_dir(subdir: Optional[str] = None) -> str:
    """Trả về đường dẫn thư mục lưu dữ liệu runtime (mặc định: data/).

    Tất cả dữ liệu phát sinh lúc chạy (logs, sessions, cache, memories, browser profiles)
    được gom vào đây để không làm bẩn thư mục source code được Git theo dõi.
    """
    base_dir = os.getenv("DATA_DIR") or "data"
    if subdir:
        path = os.path.join(base_dir, subdir)
    else:
        path = base_dir
    os.makedirs(path, exist_ok=True)
    return path


class ConfigManager:
    """Quản lý cấu hình tập trung (Single Source of Truth) có hỗ trợ env override và thread-safe."""

    CONFIG_GROUPS = (
        "app",
        "ai",
        "security",
        "monitoring",
        "cache",
        "stealth",
        "proxy",
        "dashboard",
    )

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = config_dir if config_dir is not None else (os.getenv("CONFIG_DIR") or "config")
        self.configs: Dict[str, Dict[str, Any]] = {}
        self.watchers: Dict[str, Any] = {}
        self.lock = threading.RLock()

        os.makedirs(self.config_dir, exist_ok=True)
        self.load_all_configs()

    def load_all_configs(self) -> None:
        """Load tất cả nhóm cấu hình từ file (nếu tồn tại) hoặc dùng mặc định trong bộ nhớ."""
        for config_name in self.CONFIG_GROUPS:
            self.load_config(config_name, f"{config_name}_config.json")

    def load_config(self, config_name: str, filename: str) -> Dict[str, Any]:
        """Load một nhóm cấu hình; chỉ dùng mặc định trong RAM nếu chưa có file để tránh tạo file rác."""
        with self.lock:
            defaults = self.get_default_config(config_name)
            file_path = os.path.join(self.config_dir, filename)

            try:
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        if filename.endswith((".yaml", ".yml")):
                            loaded = yaml.safe_load(f) or {}
                        else:
                            loaded = json.load(f) or {}
                    if isinstance(loaded, dict):
                        self.configs[config_name] = _deep_merge(defaults, loaded)
                    else:
                        self.configs[config_name] = defaults
                else:
                    # Không tự động ghi file mặc định xuống đĩa khi khởi tạo để giữ repo sạch sẽ khi test.
                    self.configs[config_name] = defaults

                return self._with_env_overrides(config_name, self.configs[config_name])
            except Exception as exc:
                print(f"[CONFIG] ⚠️ Lỗi đọc config {config_name}: {exc}")
                self.configs[config_name] = defaults
                return self._with_env_overrides(config_name, self.configs[config_name])

    def get_default_config(self, config_name: str) -> Dict[str, Any]:
        """Trả về bản sao cấu hình mặc định chuẩn cho từng nhóm."""
        defaults: Dict[str, Dict[str, Any]] = {
            "app": {
                "bot_name": "InstaChat",
                "version": "2.0.0",
                "debug_mode": False,
                "auto_restart": True,
                "max_retries": 3,
                "retry_delay": 5,
                "session_timeout": 3600,
                "message_delay": 3,
                "idle_threshold": 20,
                "data_dir": "data",
                "instagram_username": "",
                "instagram_password": "",
                "target_username": "",
                "target_usernames": [],
                "chrome_options": {
                    "headless": True,
                    "no_sandbox": True,
                    "disable_dev_shm_usage": True,
                    "window_size": "1366,768",
                },
                "instagram": {
                    "login_timeout": 30,
                    "message_timeout": 10,
                    "max_message_length": 1000,
                    "rate_limit_messages_per_minute": 30,
                },
            },
            "ai": {
                "api_key": "",
                "model": "gemini-flash-latest",
                "image_model": "gemini-2.5-flash-image",
                "image_provider": "gemini",
                "temperature": 0.7,
                "max_tokens": 512,
                "top_p": 0.85,
                "top_k": 40,
                "response_timeout": 30,
                "max_context_length": 4000,
                "system_prompt": (
                    "Bạn là trợ lý chat Instagram thân thiện, trả lời tự nhiên bằng ngôn ngữ của người nhắn "
                    "(ưu tiên tiếng Việt nếu người dùng nói tiếng Việt). Giữ câu trả lời ngắn gọn, tự nhiên, "
                    "đúng trọng tâm và nhớ ngữ cảnh cuộc trò chuyện."
                ),
                "memory_settings": {
                    "short_context_limit": 12,
                    "long_memory_limit": 10,
                    "memory_write_threshold": 16,
                },
                "image_generation": {
                    "enabled": True,
                    "ai_intent_detection": False,
                    "max_requests_per_hour": 20,
                    "timeout": 60,
                    "fallback_on_error": True,
                },
                "prompt_settings": {
                    "use_emoticons": True,
                    "lowercase": False,
                    "strip_emoji": False,
                    "max_response_words": 40,
                    "personality": "friendly_natural",
                },
            },
            "security": {
                "rate_limiting": {
                    "enabled": True,
                    "messages_per_minute": 30,
                    "messages_per_hour": 200,
                    "ai_requests_per_minute": 15,
                    "image_requests_per_hour": 20,
                },
                "outbound_limits": {
                    "enabled": True,
                    "messages_per_minute": 6,
                    "messages_per_hour": 60,
                    "messages_per_day": 300,
                    "min_seconds_between_replies": 4.0,
                },
                "spam_detection": {
                    "enabled": True,
                    "max_duplicate_messages": 3,
                    "max_similar_messages": 5,
                    "spam_threshold": 50,
                    "auto_block_threshold": 80,
                },
                "content_filtering": {
                    "enabled": True,
                    "max_message_length": 1000,
                    "blocked_keywords": ["hate", "violence", "illegal"],
                    "allow_links": False,
                },
                "account_protection": {
                    "max_login_attempts": 3,
                    "cooldown_minutes": 30,
                    "session_encryption": True,
                },
            },
            "monitoring": {
                "performance": {
                    "enabled": True,
                    "monitoring_interval": 10,
                    "cpu_threshold": 80,
                    "memory_threshold": 85,
                    "response_time_threshold": 5.0,
                },
                "error_tracking": {
                    "enabled": True,
                    "max_errors_per_hour": 50,
                    "auto_restart_on_critical": False,
                    "error_retention_days": 7,
                },
                "analytics": {
                    "enabled": True,
                    "data_retention_days": 30,
                    "real_time_insights": True,
                    "export_reports": True,
                },
                "notifications": {
                    "enabled": True,
                    "channels": ["console", "file"],
                    "min_level": "info",
                    "rate_limit_per_minute": 60,
                },
            },
            "cache": {
                "enabled": True,
                "cache_chat_responses": False,
                "memory_cache_size": 1000,
                "disk_cache_size_mb": 100,
                "response_cache_ttl": 3600,
                "image_cache_ttl": 86400,
                "cleanup_interval": 3600,
            },
            "stealth": {
                "enabled": True,
                "persistent_profile": True,
                "user_agent": "",
                "locale": "vi-VN",
                "timezone": "Asia/Ho_Chi_Minh",
                "human_typing": True,
                "min_typing_delay_ms": 40,
                "max_typing_delay_ms": 120,
                "reading_delay_enabled": True,
                "active_hours_start": None,
                "active_hours_end": None,
                "safety_cooldown_minutes": 30,
            },
            "proxy": {
                "url": "",
                "list": "",
                "sticky_per_account": True,
                "check_on_startup": False,
                "check_timeout_seconds": 8,
            },
            "dashboard": {
                "enabled": False,
                "host": "127.0.0.1",
                "port": 8765,
            },
        }
        return copy.deepcopy(defaults.get(config_name, {}))

    def _with_env_overrides(self, config_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Áp dụng biến môi trường lên bản sao config đọc ra mà không làm biến đổi file gốc."""
        merged = copy.deepcopy(data)

        if config_name == "app":
            if os.getenv("BOT_NAME"):
                merged["bot_name"] = os.getenv("BOT_NAME")
            if os.getenv("DATA_DIR"):
                merged["data_dir"] = os.getenv("DATA_DIR")
            if os.getenv("INSTAGRAM_USERNAME"):
                merged["instagram_username"] = os.getenv("INSTAGRAM_USERNAME")
            if os.getenv("INSTAGRAM_PASSWORD"):
                merged["instagram_password"] = os.getenv("INSTAGRAM_PASSWORD")
            if os.getenv("TARGET_USERNAME"):
                merged["target_username"] = os.getenv("TARGET_USERNAME")
            if os.getenv("TARGET_USERNAMES"):
                targets = [
                    item.strip().lstrip("@")
                    for item in os.getenv("TARGET_USERNAMES", "").split(",")
                    if item.strip()
                ]
                merged["target_usernames"] = targets
            merged["message_delay"] = _parse_float(
                os.getenv("MESSAGE_DELAY"), float(merged.get("message_delay", 3))
            )
            merged["idle_threshold"] = _parse_int(
                os.getenv("IDLE_THRESHOLD"), merged.get("idle_threshold", 20)
            )
            chrome = merged.setdefault("chrome_options", {})
            chrome["headless"] = _parse_bool(
                os.getenv("CHROME_HEADLESS"), bool(chrome.get("headless", True))
            )
            if os.getenv("CHROME_WINDOW_SIZE"):
                chrome["window_size"] = os.getenv("CHROME_WINDOW_SIZE")

        elif config_name == "ai":
            if os.getenv("GEMINI_API_KEY"):
                merged["api_key"] = os.getenv("GEMINI_API_KEY")
            if os.getenv("GEMINI_MODEL"):
                merged["model"] = os.getenv("GEMINI_MODEL")
            if os.getenv("GEMINI_IMAGE_MODEL"):
                merged["image_model"] = os.getenv("GEMINI_IMAGE_MODEL")
            if os.getenv("BOT_SYSTEM_PROMPT"):
                merged["system_prompt"] = os.getenv("BOT_SYSTEM_PROMPT")
            prompt_settings = merged.setdefault("prompt_settings", {})
            prompt_settings["max_response_words"] = _parse_int(
                os.getenv("MAX_RESPONSE_WORDS"),
                prompt_settings.get("max_response_words", 40),
            )

        elif config_name == "security":
            rate_cfg = merged.setdefault("rate_limiting", {})
            rate_cfg["messages_per_minute"] = _parse_int(
                os.getenv("RATE_LIMIT_MESSAGES"), rate_cfg.get("messages_per_minute", 30)
            )
            acct_cfg = merged.setdefault("account_protection", {})
            acct_cfg["max_login_attempts"] = _parse_int(
                os.getenv("MAX_LOGIN_ATTEMPTS"), acct_cfg.get("max_login_attempts", 3)
            )
            outbound = merged.setdefault("outbound_limits", {})
            outbound["messages_per_minute"] = _parse_int(
                os.getenv("OUTBOUND_MESSAGES_PER_MINUTE"),
                outbound.get("messages_per_minute", 6),
            )
            outbound["messages_per_hour"] = _parse_int(
                os.getenv("OUTBOUND_MESSAGES_PER_HOUR"),
                outbound.get("messages_per_hour", 60),
            )
            outbound["messages_per_day"] = _parse_int(
                os.getenv("OUTBOUND_MESSAGES_PER_DAY"),
                outbound.get("messages_per_day", 300),
            )
            outbound["min_seconds_between_replies"] = _parse_float(
                os.getenv("MIN_SECONDS_BETWEEN_REPLIES"),
                float(outbound.get("min_seconds_between_replies", 4.0)),
            )

        elif config_name == "monitoring":
            perf = merged.setdefault("performance", {})
            perf["monitoring_interval"] = _parse_int(
                os.getenv("PERFORMANCE_CHECK_INTERVAL"), perf.get("monitoring_interval", 10)
            )
            perf["cpu_threshold"] = _parse_int(
                os.getenv("CPU_ALERT_THRESHOLD"), perf.get("cpu_threshold", 80)
            )
            perf["memory_threshold"] = _parse_int(
                os.getenv("MEMORY_ALERT_THRESHOLD"), perf.get("memory_threshold", 85)
            )
            perf["response_time_threshold"] = _parse_float(
                os.getenv("RESPONSE_TIME_THRESHOLD"),
                float(perf.get("response_time_threshold", 5.0)),
            )

        elif config_name == "stealth":
            merged["persistent_profile"] = _parse_bool(
                os.getenv("CHROME_PERSISTENT_PROFILE"),
                bool(merged.get("persistent_profile", True)),
            )
            if os.getenv("CHROME_USER_AGENT") is not None and os.getenv("CHROME_USER_AGENT") != "":
                merged["user_agent"] = os.getenv("CHROME_USER_AGENT")
            start_hour = _parse_int(os.getenv("ACTIVE_HOURS_START"), merged.get("active_hours_start"))
            end_hour = _parse_int(os.getenv("ACTIVE_HOURS_END"), merged.get("active_hours_end"))
            merged["active_hours_start"] = start_hour
            merged["active_hours_end"] = end_hour

        elif config_name == "proxy":
            if os.getenv("PROXY_URL"):
                merged["url"] = os.getenv("PROXY_URL")
            if os.getenv("PROXY_LIST"):
                merged["list"] = os.getenv("PROXY_LIST")
            merged["check_on_startup"] = _parse_bool(
                os.getenv("PROXY_CHECK_ON_STARTUP"),
                bool(merged.get("check_on_startup", False)),
            )

        elif config_name == "dashboard":
            merged["enabled"] = _parse_bool(
                os.getenv("DASHBOARD_ENABLED"), bool(merged.get("enabled", False))
            )
            if os.getenv("DASHBOARD_HOST"):
                merged["host"] = os.getenv("DASHBOARD_HOST")
            merged["port"] = _parse_int(os.getenv("DASHBOARD_PORT"), merged.get("port", 8765))

        return merged

    def save_config(self, config_name: str, filename: Optional[str] = None) -> bool:
        """Lưu cấu hình ra file trong config_dir."""
        with self.lock:
            if config_name not in self.configs:
                return False

            if not filename:
                filename = f"{config_name}_config.json"

            file_path = os.path.join(self.config_dir, filename)
            os.makedirs(self.config_dir, exist_ok=True)

            try:
                config_data = copy.deepcopy(self.configs[config_name])
                config_data["_metadata"] = {
                    "last_updated": datetime.now().isoformat(),
                    "version": "2.0.0",
                }
                with open(file_path, "w", encoding="utf-8") as f:
                    if filename.endswith((".yaml", ".yml")):
                        yaml.safe_dump(config_data, f, default_flow_style=False, allow_unicode=True)
                    else:
                        json.dump(config_data, f, indent=2, ensure_ascii=False)
                return True
            except Exception as exc:
                print(f"[CONFIG] ❌ Lỗi lưu config {config_name}: {exc}")
                return False

    def get(self, config_name: str, key: Any = None, default: Any = None) -> Any:
        """Lấy giá trị config hỗ trợ dot-notation và bảo vệ trước tham số key sai kiểu."""
        with self.lock:
            if config_name not in self.configs:
                return default

            config = self._with_env_overrides(config_name, self.configs[config_name])

            if key is None:
                return config

            # Phòng ngừa lỗi cũ khi caller truyền nhầm dict {} làm tham số thứ 2 thay vì key string.
            if not isinstance(key, str):
                if isinstance(key, dict):
                    return config if config is not None else key
                return default

            value: Any = config
            for part in key.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value

    def set(self, config_name: str, key: str, value: Any, save: bool = True) -> None:
        """Cập nhật một khóa cấu hình theo dot-notation."""
        with self.lock:
            if config_name not in self.configs:
                self.configs[config_name] = self.get_default_config(config_name)

            parts = key.split(".")
            current = self.configs[config_name]
            for part in parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value

            if save:
                self.save_config(config_name)

    def update(self, config_name: str, updates: Dict[str, Any], save: bool = True) -> None:
        """Cập nhật hàng loạt khóa cấu hình (deep merge)."""
        with self.lock:
            if config_name not in self.configs:
                self.configs[config_name] = self.get_default_config(config_name)
            self.configs[config_name] = _deep_merge(self.configs[config_name], updates)
            if save:
                self.save_config(config_name)

    def reload_config(self, config_name: str) -> Dict[str, Any]:
        return self.load_config(config_name, f"{config_name}_config.json")

    def reload_all_configs(self) -> None:
        self.load_all_configs()

    def validate_config(self, config_name: str) -> Tuple[bool, List[str]]:
        """Kiểm tra tính hợp lệ của một nhóm cấu hình."""
        errors: List[str] = []
        if config_name not in self.configs:
            return False, [f"Config '{config_name}' not found"]

        config = self.get(config_name)
        if config_name == "app":
            if not config.get("bot_name"):
                errors.append("bot_name is required")
            if config.get("max_retries", 0) < 0:
                errors.append("max_retries must be >= 0")
        elif config_name == "ai":
            if not config.get("model"):
                errors.append("AI model is required")
            temp = config.get("temperature", 0.7)
            if not (0 <= temp <= 2):
                errors.append("temperature must be between 0 and 2")
        elif config_name == "security":
            rate_limit = config.get("rate_limiting", {})
            if (rate_limit.get("messages_per_minute") or 0) <= 0:
                errors.append("messages_per_minute must be > 0")
            outbound = config.get("outbound_limits", {})
            if (outbound.get("messages_per_minute") or 0) <= 0:
                errors.append("outbound messages_per_minute must be > 0")
        elif config_name == "dashboard":
            port = config.get("port", 8765)
            if not isinstance(port, int) or not (0 <= port <= 65535):
                errors.append("dashboard port must be between 0 and 65535")

        return len(errors) == 0, errors

    def get_config_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {"total_configs": len(self.configs), "configs": {}}
        for name, data in self.configs.items():
            summary["configs"][name] = {
                "keys_count": len(data),
                "has_metadata": "_metadata" in data,
                "last_updated": data.get("_metadata", {}).get("last_updated", "in-memory"),
            }
        return summary

    def export_all_configs(self, filename: Optional[str] = None) -> bool:
        if not filename:
            filename = f"config_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        export_path = os.path.join(self.config_dir, filename)
        try:
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "configs": self.configs,
            }
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            print(f"[CONFIG] ❌ Lỗi export config: {exc}")
            return False

    def import_configs(self, filename: str) -> bool:
        import_path = os.path.join(self.config_dir, filename)
        if not os.path.exists(import_path):
            return False
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                import_data = json.load(f)
            if isinstance(import_data, dict) and isinstance(import_data.get("configs"), dict):
                self.configs.update(import_data["configs"])
                for config_name in import_data["configs"]:
                    self.save_config(config_name)
                return True
            return False
        except Exception as exc:
            print(f"[CONFIG] ❌ Lỗi import config: {exc}")
            return False

    def print_config_summary(self) -> None:
        summary = self.get_config_summary()
        print("\n[CONFIG] ⚙️ === CONFIG SUMMARY ===")
        print(f"[CONFIG] 📊 Total Configs: {summary['total_configs']}")
        for name, info in summary["configs"].items():
            is_valid, errors = self.validate_config(name)
            status = "✅ Valid" if is_valid else f"❌ Invalid ({len(errors)} errors)"
            print(f"[CONFIG]   - {name}: {info['keys_count']} keys | {status}")
        print("[CONFIG] ================================\n")


_config_manager: Optional[ConfigManager] = None
_config_lock = threading.Lock()


def get_config_manager(config_dir: Optional[str] = None) -> ConfigManager:
    """Lấy singleton ConfigManager (thread-safe)."""
    global _config_manager
    with _config_lock:
        if _config_manager is None:
            _config_manager = ConfigManager(config_dir=config_dir)
        return _config_manager


def reset_config_manager() -> None:
    """Reset singleton để phục vụ unit test cô lập."""
    global _config_manager
    with _config_lock:
        _config_manager = None


def get_config(config_name: str, key: Any = None, default: Any = None) -> Any:
    return get_config_manager().get(config_name, key, default)


def set_config(config_name: str, key: str, value: Any, save: bool = True) -> None:
    get_config_manager().set(config_name, key, value, save)


def reload_config(config_name: Optional[str] = None) -> Any:
    manager = get_config_manager()
    if config_name:
        return manager.reload_config(config_name)
    return manager.reload_all_configs()
