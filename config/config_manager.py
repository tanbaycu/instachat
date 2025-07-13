import json
import os
import yaml
from datetime import datetime
from typing import Any, Dict, Optional
import threading


class ConfigManager:
    def __init__(self, config_dir="config"):
        self.config_dir = config_dir
        self.configs = {}
        self.watchers = {}
        self.lock = threading.RLock()
        
        # Tạo thư mục config
        os.makedirs(config_dir, exist_ok=True)
        
        # Load all configs
        self.load_all_configs()
        
        print("[CONFIG] ⚙️ Config Manager đã khởi tạo")

    def load_all_configs(self):
        """Load tất cả config files"""
        config_files = [
            'app_config.json',
            'ai_config.json', 
            'security_config.json',
            'monitoring_config.json',
            'cache_config.json'
        ]
        
        for config_file in config_files:
            config_name = config_file.split('_')[0]  # app, ai, security, etc.
            self.load_config(config_name, config_file)

    def load_config(self, config_name: str, filename: str) -> Dict[str, Any]:
        """Load config từ file"""
        with self.lock:
            file_path = os.path.join(self.config_dir, filename)
            
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        if filename.endswith('.yaml') or filename.endswith('.yml'):
                            config_data = yaml.safe_load(f)
                        else:
                            config_data = json.load(f)
                    
                    self.configs[config_name] = config_data
                    print(f"[CONFIG] 📂 Loaded {config_name} config from {filename}")
                else:
                    # Tạo config mặc định
                    default_config = self.get_default_config(config_name)
                    self.configs[config_name] = default_config
                    self.save_config(config_name, filename)
                    print(f"[CONFIG] 📝 Created default {config_name} config")
                
                return self.configs[config_name]
                
            except Exception as e:
                print(f"[CONFIG] ❌ Error loading {config_name}: {str(e)}")
                # Fallback to default
                self.configs[config_name] = self.get_default_config(config_name)
                return self.configs[config_name]

    def get_default_config(self, config_name: str) -> Dict[str, Any]:
        """Lấy default config cho từng loại"""
        defaults = {
            'app': {
                'bot_name': 'InstaChatBot',
                'version': '1.0.0',
                'debug_mode': False,
                'auto_restart': True,
                'max_retries': 3,
                'retry_delay': 5,
                'session_timeout': 3600,
                'chrome_options': {
                    'headless': True,
                    'no_sandbox': True,
                    'disable_dev_shm_usage': True,
                    'window_size': '1920,1080'
                },
                'instagram': {
                    'login_timeout': 30,
                    'message_timeout': 10,
                    'max_message_length': 1000,
                    'rate_limit_messages_per_minute': 30
                }
            },
            'ai': {
                'model': 'gemini-2.0-flash',
                'temperature': 0.7,
                'max_tokens': 1024,
                'top_p': 0.8,
                'top_k': 70,
                'response_timeout': 30,
                'max_context_length': 4000,
                'memory_settings': {
                    'short_context_limit': 10,
                    'long_memory_limit': 12,
                    'memory_write_threshold': 16
                },
                'image_generation': {
                    'enabled': True,
                    'max_requests_per_hour': 20,
                    'timeout': 60,
                    'fallback_on_error': True
                },
                'prompt_settings': {
                    'use_emoticons': True,
                    'max_response_length': 200,
                    'personality': 'friendly_gen_z'
                }
            },
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'messages_per_minute': 30,
                    'messages_per_hour': 200,
                    'ai_requests_per_minute': 10,
                    'image_requests_per_hour': 20
                },
                'spam_detection': {
                    'enabled': True,
                    'max_duplicate_messages': 3,
                    'max_similar_messages': 5,
                    'spam_threshold': 50,
                    'auto_block_threshold': 80
                },
                'content_filtering': {
                    'enabled': True,
                    'max_message_length': 1000,
                    'blocked_keywords': ['spam', 'scam', 'hack'],
                    'allow_links': False
                },
                'account_protection': {
                    'max_login_attempts': 3,
                    'cooldown_minutes': 30,
                    'session_encryption': True
                }
            },
            'monitoring': {
                'performance': {
                    'enabled': True,
                    'monitoring_interval': 5,
                    'cpu_threshold': 80,
                    'memory_threshold': 80,
                    'response_time_threshold': 10
                },
                'error_tracking': {
                    'enabled': True,
                    'max_errors_per_hour': 50,
                    'auto_restart_on_critical': True,
                    'error_retention_days': 7
                },
                'analytics': {
                    'enabled': True,
                    'data_retention_days': 30,
                    'real_time_insights': True,
                    'export_reports': True
                },
                'notifications': {
                    'enabled': True,
                    'channels': ['console', 'file'],
                    'min_level': 'info',
                    'rate_limit_per_minute': 60
                }
            },
            'cache': {
                'enabled': True,
                'memory_cache_size': 1000,
                'disk_cache_size_mb': 100,
                'response_cache_ttl': 7200,
                'image_cache_ttl': 86400,
                'cleanup_interval': 3600
            }
        }
        
        return defaults.get(config_name, {})

    def save_config(self, config_name: str, filename: str = None):
        """Lưu config vào file"""
        with self.lock:
            if config_name not in self.configs:
                return False
            
            if not filename:
                filename = f"{config_name}_config.json"
            
            file_path = os.path.join(self.config_dir, filename)
            
            try:
                config_data = self.configs[config_name].copy()
                config_data['_metadata'] = {
                    'last_updated': datetime.now().isoformat(),
                    'version': '1.0.0'
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    if filename.endswith('.yaml') or filename.endswith('.yml'):
                        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                    else:
                        json.dump(config_data, f, indent=2, ensure_ascii=False)
                
                print(f"[CONFIG] 💾 Saved {config_name} config to {filename}")
                return True
                
            except Exception as e:
                print(f"[CONFIG] ❌ Error saving {config_name}: {str(e)}")
                return False

    def get(self, config_name: str, key: str = None, default: Any = None) -> Any:
        """Lấy giá trị config"""
        with self.lock:
            if config_name not in self.configs:
                return default
            
            config = self.configs[config_name]
            
            if key is None:
                return config
            
            # Support nested keys với dot notation
            keys = key.split('.')
            value = config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value

    def set(self, config_name: str, key: str, value: Any, save: bool = True):
        """Set giá trị config"""
        with self.lock:
            if config_name not in self.configs:
                self.configs[config_name] = {}
            
            config = self.configs[config_name]
            
            # Support nested keys với dot notation
            keys = key.split('.')
            current = config
            
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            current[keys[-1]] = value
            
            if save:
                self.save_config(config_name)
            
            print(f"[CONFIG] ✏️ Updated {config_name}.{key} = {value}")

    def update(self, config_name: str, updates: Dict[str, Any], save: bool = True):
        """Update multiple config values"""
        with self.lock:
            if config_name not in self.configs:
                self.configs[config_name] = {}
            
            def deep_update(base_dict, update_dict):
                for key, value in update_dict.items():
                    if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                        deep_update(base_dict[key], value)
                    else:
                        base_dict[key] = value
            
            deep_update(self.configs[config_name], updates)
            
            if save:
                self.save_config(config_name)
            
            print(f"[CONFIG] 🔄 Updated {config_name} with {len(updates)} changes")

    def reload_config(self, config_name: str):
        """Reload config từ file"""
        filename = f"{config_name}_config.json"
        return self.load_config(config_name, filename)

    def reload_all_configs(self):
        """Reload tất cả configs"""
        print("[CONFIG] 🔄 Reloading all configs...")
        self.load_all_configs()

    def validate_config(self, config_name: str) -> tuple[bool, list]:
        """Validate config"""
        errors = []
        
        if config_name not in self.configs:
            errors.append(f"Config '{config_name}' not found")
            return False, errors
        
        config = self.configs[config_name]
        
        # Validation rules cho từng config type
        if config_name == 'app':
            if not config.get('bot_name'):
                errors.append("bot_name is required")
            if config.get('max_retries', 0) < 0:
                errors.append("max_retries must be >= 0")
        
        elif config_name == 'ai':
            if not config.get('model'):
                errors.append("AI model is required")
            if not (0 <= config.get('temperature', 0.7) <= 2):
                errors.append("temperature must be between 0 and 2")
        
        elif config_name == 'security':
            rate_limit = config.get('rate_limiting', {})
            if rate_limit.get('messages_per_minute', 30) <= 0:
                errors.append("messages_per_minute must be > 0")
        
        return len(errors) == 0, errors

    def get_config_summary(self):
        """Lấy tóm tắt tất cả configs"""
        summary = {
            'total_configs': len(self.configs),
            'configs': {}
        }
        
        for config_name, config_data in self.configs.items():
            summary['configs'][config_name] = {
                'keys_count': len(config_data),
                'has_metadata': '_metadata' in config_data,
                'last_updated': config_data.get('_metadata', {}).get('last_updated', 'unknown')
            }
        
        return summary

    def export_all_configs(self, filename: str = None):
        """Export tất cả configs ra file"""
        if not filename:
            filename = f"config_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        export_path = os.path.join(self.config_dir, filename)
        
        try:
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'configs': self.configs
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            print(f"[CONFIG] 📦 Exported all configs to {filename}")
            return True
            
        except Exception as e:
            print(f"[CONFIG] ❌ Export error: {str(e)}")
            return False

    def import_configs(self, filename: str):
        """Import configs từ file"""
        import_path = os.path.join(self.config_dir, filename)
        
        if not os.path.exists(import_path):
            print(f"[CONFIG] ❌ Import file not found: {filename}")
            return False
        
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            if 'configs' in import_data:
                self.configs.update(import_data['configs'])
                
                # Save all imported configs
                for config_name in import_data['configs'].keys():
                    self.save_config(config_name)
                
                print(f"[CONFIG] 📥 Imported {len(import_data['configs'])} configs")
                return True
            else:
                print(f"[CONFIG] ❌ Invalid import file format")
                return False
                
        except Exception as e:
            print(f"[CONFIG] ❌ Import error: {str(e)}")
            return False

    def print_config_summary(self):
        """In tóm tắt configs"""
        summary = self.get_config_summary()
        
        print(f"\n[CONFIG] ⚙️ === CONFIG SUMMARY ===")
        print(f"[CONFIG] 📊 Total Configs: {summary['total_configs']}")
        
        for config_name, info in summary['configs'].items():
            print(f"[CONFIG] 📋 {config_name}:")
            print(f"[CONFIG]   - Keys: {info['keys_count']}")
            print(f"[CONFIG]   - Last Updated: {info['last_updated']}")
            
            # Validate config
            is_valid, errors = self.validate_config(config_name)
            if is_valid:
                print(f"[CONFIG]   - Status: ✅ Valid")
            else:
                print(f"[CONFIG]   - Status: ❌ Invalid ({len(errors)} errors)")
        
        print(f"[CONFIG] ================================\n")


# Singleton instance
_config_manager = None

def get_config_manager():
    """Lấy instance singleton của ConfigManager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


# Convenience functions
def get_config(config_name: str, key: str = None, default: Any = None):
    """Convenience function để lấy config"""
    return get_config_manager().get(config_name, key, default)

def set_config(config_name: str, key: str, value: Any, save: bool = True):
    """Convenience function để set config"""
    return get_config_manager().set(config_name, key, value, save)

def reload_config(config_name: str = None):
    """Convenience function để reload config"""
    config_manager = get_config_manager()
    if config_name:
        return config_manager.reload_config(config_name)
    else:
        return config_manager.reload_all_configs()


if __name__ == "__main__":
    # Test config manager
    config_mgr = get_config_manager()
    
    # Test get/set
    print(f"App name: {config_mgr.get('app', 'bot_name')}")
    config_mgr.set('app', 'debug_mode', True)
    
    # Test nested keys
    print(f"AI temperature: {config_mgr.get('ai', 'temperature')}")
    config_mgr.set('ai', 'memory_settings.short_context_limit', 15)
    
    # Test validation
    is_valid, errors = config_mgr.validate_config('app')
    print(f"App config valid: {is_valid}")
    
    # Print summary
    config_mgr.print_config_summary()
    
    # Test export
    config_mgr.export_all_configs("test_export.json") 