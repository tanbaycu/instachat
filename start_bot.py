#!/usr/bin/env python3
"""
InstaChat v2.0 Startup & CLI Launcher.
Hỗ trợ 4 chế độ: run (Instagram bot), cli (chat terminal), check (health check), dashboard (Web UI).
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def check_python_version() -> bool:
    if sys.version_info < (3, 10):
        print(f"❌ Yêu cầu Python 3.10+. Hiện tại: {sys.version}")
        return False
    print(f"✅ Python: {sys.version.split()[0]}")
    return True


def ensure_directories() -> None:
    from config.config_manager import get_data_dir

    for subdir in ("logs", "sessions", "memories", "cache", "analytics", "profiles", "generated_images"):
        get_data_dir(subdir)
    print(f"✅ Thư mục runtime: {get_data_dir()}")


def install_requirements() -> bool:
    if not os.path.exists("requirements.txt"):
        print("❌ Không tìm thấy requirements.txt")
        return False
    print("📥 Đang cài đặt dependencies từ requirements.txt...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
        return False
    print("✅ Cài đặt dependencies thành công!")
    return True


def check_imports() -> bool:
    required = [
        ("selenium", "selenium"),
        ("google.genai", "google-genai"),
        ("psutil", "psutil"),
        ("cryptography", "cryptography"),
        ("requests", "requests"),
        ("yaml", "pyyaml"),
        ("PIL", "pillow"),
    ]
    missing: List[str] = []
    for mod, pkg in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"❌ Thiếu package: {', '.join(missing)}")
        print(f"💡 Chạy: {sys.executable} -m pip install {' '.join(missing)}")
        return False
    print("✅ Tất cả thư viện bắt buộc đều sẵn sàng.")
    return True


def detect_chrome_binary() -> Optional[str]:
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def run_environment_check() -> bool:
    print("\n" + "=" * 56)
    print("🤖 INSTACHAT v2.0 — ENVIRONMENT HEALTH CHECK")
    print("=" * 56)

    ok = True
    if not check_python_version():
        ok = False

    ensure_directories()

    if not check_imports():
        ok = False

    chrome_path = detect_chrome_binary()
    if chrome_path:
        print(f"✅ Chrome/Chromium: {chrome_path}")
    else:
        print("⚠️ Chưa tìm thấy Chrome/Chromium trên PATH (chỉ cần cho chế độ --mode run)")

    from config.config_manager import get_config_manager

    cfg = get_config_manager()
    for group in cfg.CONFIG_GROUPS:
        valid, errs = cfg.validate_config(group)
        if valid:
            print(f"✅ Config '{group}': hợp lệ")
        else:
            print(f"❌ Config '{group}' lỗi: {errs}")
            ok = False

    api_key = os.getenv("GEMINI_API_KEY") or cfg.get("ai", "api_key")
    if api_key and api_key != "your_gemini_api_key_here":
        print(f"✅ GEMINI_API_KEY: đã cấu hình (model={cfg.get('ai', 'model')})")
    else:
        print("⚠️ GEMINI_API_KEY: chưa cấu hình (chế độ sandbox demo vẫn dùng được)")

    ig_user = os.getenv("INSTAGRAM_USERNAME") or cfg.get("app", "instagram_username")
    ig_target = os.getenv("TARGET_USERNAME") or cfg.get("app", "target_username")
    if ig_user and ig_target:
        print(f"✅ Instagram config: @{ig_user} -> @{ig_target}")
    else:
        print("⚠️ Instagram credentials: chưa điền đủ trong .env")

    proxy_cfg = cfg.get("proxy") or {}
    if proxy_cfg.get("url") or proxy_cfg.get("list"):
        from automation.proxy_manager import ProxyPool

        pool = ProxyPool(proxy_url=proxy_cfg.get("url"), proxy_list=proxy_cfg.get("list"))
        print(f"✅ ProxyPool: đã nạp {len(pool.proxies)} proxy")
        if proxy_cfg.get("check_on_startup") and pool.proxies:
            healthy, info = pool.check_health(pool.proxies[0])
            print(f"   Proxy check: {'OK -> IP ' + info if healthy else 'FAIL -> ' + info}")

    print("=" * 56 + "\n")
    return ok


def run_cli_chat() -> int:
    """Chế độ chat tương tác trực tiếp trên terminal để test AI & SQLite Memory."""
    from core import cleanup_insta_bot, create_insta_bot

    print("\n" + "=" * 56)
    print("💬 INSTACHAT CLI SANDBOX (gõ /help để xem lệnh)")
    print("=" * 56)

    try:
        bot = create_insta_bot()
    except Exception as exc:
        print(f"❌ Không thể khởi tạo AI Bot: {exc}")
        print("💡 Hãy thiết lập GEMINI_API_KEY trong file .env trước khi chạy --mode cli.")
        return 1

    username = os.getenv("TARGET_USERNAME") or "cli_user"
    try:
        while True:
            try:
                user_msg = input(f"\n[{username}] > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Thoát CLI chat.")
                break

            if not user_msg:
                continue
            if user_msg in {"/exit", "/quit"}:
                break
            if user_msg == "/help":
                print("Lệnh hỗ trợ: /stats, /memory, /clear, /exit")
                continue
            if user_msg == "/stats":
                print(bot.get_memory_stats(username=username))
                continue
            if user_msg == "/memory":
                print(bot.memory_store.get_short_context_lines(username))
                continue
            if user_msg == "/clear":
                bot.clear_short_memory(username=username)
                print("🗑️ Đã xóa ngữ cảnh ngắn hạn.")
                continue

            reply = bot.generate_response(user_msg, username=username)
            print(f"[InstaChat] {reply}")
    finally:
        cleanup_insta_bot(bot)

    return 0


def run_standalone_dashboard(host: str, port: int) -> int:
    from dashboard.server import DashboardServer

    server = DashboardServer(host=host, port=port)
    server.set_runtime_state(running=True, mode="dashboard")
    server.start()
    print(f"🌐 Dashboard đang chạy tại {server.base_url} (nhấn Ctrl+C để dừng)")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n🛑 Đang dừng Dashboard...")
    finally:
        server.stop()
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="InstaChat v2.0 Launcher")
    parser.add_argument(
        "--mode",
        choices=("run", "cli", "check", "dashboard"),
        default="run",
        help="Chế độ chạy: run (bot Instagram), cli (terminal), check (kiểm tra), dashboard (web UI)",
    )
    parser.add_argument("--dashboard", action="store_true", help="Bật kèm Web Dashboard khi chạy bot")
    parser.add_argument("--install", action="store_true", help="Cài đặt requirements trước khi chạy")
    parser.add_argument("--skip-install", action="store_true", help="Bỏ qua bước kiểm tra/cài đặt pip")
    parser.add_argument("--target", type=str, default=None, help="Username Instagram mục tiêu")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy URL (vd: http://user:pass@host:port)")
    parser.add_argument("--headless", dest="headless", action="store_true", default=None)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--host", type=str, default=None, help="Host cho Dashboard")
    parser.add_argument("--port", type=int, default=None, help="Port cho Dashboard")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.install and not args.skip_install:
        if not install_requirements():
            return 1

    if args.mode == "check":
        return 0 if run_environment_check() else 1

    if not check_python_version() or not check_imports():
        return 1
    ensure_directories()

    from config.config_manager import get_config_manager

    dash_cfg = get_config_manager().get("dashboard") or {}
    host = args.host or dash_cfg.get("host", "127.0.0.1")
    port = int(args.port or dash_cfg.get("port", 8765))

    if args.mode == "dashboard":
        return run_standalone_dashboard(host, port)

    if args.mode == "cli":
        return run_cli_chat()

    from app import run_app

    overrides = {
        "target": args.target,
        "proxy_url": args.proxy,
        "headless": args.headless,
        "dashboard_host": host,
        "dashboard_port": port,
    }
    return run_app(config_overrides=overrides, start_dashboard=bool(args.dashboard))


if __name__ == "__main__":
    raise SystemExit(main())
