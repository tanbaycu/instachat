import os

from config.config_manager import ConfigManager, get_config_manager


def test_config_manager_does_not_create_files_until_saved(tmp_path):
    cfg_dir = tmp_path / "cfg"
    mgr = ConfigManager(config_dir=str(cfg_dir))

    assert mgr.get("app", "bot_name") == "InstaChat"
    assert list(cfg_dir.iterdir()) == []

    mgr.set("app", "bot_name", "CustomBot", save=True)
    assert (cfg_dir / "app_config.json").exists()

    reloaded = ConfigManager(config_dir=str(cfg_dir))
    assert reloaded.get("app", "bot_name") == "CustomBot"


def test_config_manager_safe_get_handles_non_string_key():
    mgr = get_config_manager()
    app_cfg = mgr.get("app", {})
    assert isinstance(app_cfg, dict)
    assert app_cfg["bot_name"] == "InstaChat"
    assert mgr.get("app", 12345, "fallback") == "fallback"


def test_config_manager_env_overrides(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom-test")
    monkeypatch.setenv("CHROME_HEADLESS", "false")
    monkeypatch.setenv("OUTBOUND_MESSAGES_PER_HOUR", "42")
    monkeypatch.setenv("TARGET_USERNAMES", "@alice, bob ")

    mgr = get_config_manager()
    assert mgr.get("ai", "model") == "gemini-custom-test"
    assert mgr.get("app", "chrome_options.headless") is False
    assert mgr.get("security", "outbound_limits.messages_per_hour") == 42
    assert mgr.get("app", "target_usernames") == ["alice", "bob"]


def test_config_validation():
    mgr = get_config_manager()
    for group in mgr.CONFIG_GROUPS:
        valid, errors = mgr.validate_config(group)
        assert valid is True, f"{group} failed validation: {errors}"

    mgr.set("ai", "temperature", 5.0, save=False)
    valid, errors = mgr.validate_config("ai")
    assert valid is False
    assert errors
    assert os.path.isdir(mgr.config_dir)
