import os
import sys

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def _reset_all_singletons():
    from analytics.analytics_engine import reset_analytics_engine
    from analytics.conversation_insights import reset_conversation_insights
    from config.config_manager import reset_config_manager
    from monitoring.error_handler import reset_error_handler
    from monitoring.performance_monitor import reset_performance_monitor
    from security.security_manager import reset_security_manager
    from security.session_manager import reset_session_manager
    from utils.cache_manager import reset_cache_managers
    from utils.notification_system import reset_notification_system

    reset_notification_system()
    reset_performance_monitor()
    reset_error_handler()
    reset_cache_managers()
    reset_security_manager()
    reset_session_manager()
    reset_conversation_insights()
    reset_analytics_engine()
    reset_config_manager()


@pytest.fixture(autouse=True)
def isolated_runtime_env(tmp_path, monkeypatch):
    """Cô lập DATA_DIR, CONFIG_DIR và reset toàn bộ singleton sau mỗi test."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("PROXY_URL", raising=False)
    monkeypatch.delenv("PROXY_LIST", raising=False)

    _reset_all_singletons()
    yield tmp_path
    _reset_all_singletons()
