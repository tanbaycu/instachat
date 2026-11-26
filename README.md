# InstaChat v2.0

[![CI](https://github.com/tanbaycu/instachat/actions/workflows/ci.yml/badge.svg)](https://github.com/tanbaycu/instachat/actions/workflows/ci.yml)
[![CodeQL](https://github.com/tanbaycu/instachat/actions/workflows/codeql.yml/badge.svg)](https://github.com/tanbaycu/instachat/actions/workflows/codeql.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Instagram Direct AI automation powered by Google Gemini (`google-genai`), built with anti-detection browser fingerprinting, sticky proxy rotation, per-user SQLite memory, outbound rate-limit budgets, and a live telemetry dashboard.**

---

## Architecture Overview

```mermaid
flowchart LR
    IG["Instagram Direct (Selenium 4 + CDP Stealth)"] --> L["Listener & Noise Filter"]
    L --> S["SecurityManager (Spam Filter & Outbound Budget)"]
    S --> AI["InstaBot (google-genai) + ImageGenerator"]
    AI <--> MEM["SQLiteMemoryStore (Per-User Context)"]
    AI --> SEND["HumanBehavior Typing & File Upload"]
    SEND --> IG
    PX["Sticky ProxyPool + MV3 Auth Ext"] --> IG
    DASH["Telemetry Dashboard & AI Sandbox (:8765)"] <--> AI
    DASH <--> S
```

---

## Key Capabilities

| Area | Implementation |
| --- | --- |
| **AI Engine** | Official `google-genai` SDK (`gemini-flash-latest`), retry with exponential backoff + jitter, bilingual EN/VI response post-processing. |
| **Image Generation** | Native Gemini Image Generation (`gemini-2.5-flash-image`), strict action-intent regex (no false positives), local file output & Direct upload. |
| **Anti-Detection** | Persistent browser profiles, consistent per-account `BrowserFingerprint` (viewport, WebGL, locale, timezone), CDP stealth script (`navigator.webdriver` masking), human-paced typing (including non-BMP emoji via JS), and configurable `ACTIVE_HOURS`. |
| **Proxy & Resilience** | Sticky `ProxyPool` supporting HTTP/HTTPS/SOCKS5 (`host:port` & `user:pass` via generated MV3 Chrome auth extension), startup health checks, automatic proxy failover, and WebDriver crash recovery. |
| **Rate-Limit & Safety** | Per-minute / per-hour / per-day outbound reply budget (`SecurityManager`), minimum reply cooldown, encrypted JSON session cookies (Fernet, zero `pickle`), and early `AccountSafetyDetector` halt on challenge/2FA/rate-limit banners. |
| **Memory & Analytics** | Per-user `SQLiteMemoryStore` (`data/memories/memory.db`) and pure-stdlib bilingual sentiment, session detection, TF-IDF clustering, and topic centrality analytics. |
| **Observability** | Built-in HTTP Telemetry Dashboard (`127.0.0.1:8765`) with CPU/RAM health score, outbound budget meters, Pause/Resume controls, and interactive AI Sandbox Chat. |

---

## Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/tanbaycu/instachat.git
cd instachat
python -m venv .venv
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Linux / macOS:**
```bash
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Set your credentials in `.env`:

| Variable | Description | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Google AI Studio API key | *(required for AI)* |
| `GEMINI_MODEL` | Text model ID | `gemini-flash-latest` |
| `GEMINI_IMAGE_MODEL` | Native image generation model ID | `gemini-2.5-flash-image` |
| `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | Instagram account credentials | *(required for `run`)* |
| `TARGET_USERNAME` / `TARGET_USERNAMES` | Single or comma-separated target handles | — |
| `PROXY_URL` / `PROXY_LIST` | `http://user:pass@host:port`, `socks5://...`, or proxy list file | — |
| `OUTBOUND_MESSAGES_PER_MINUTE` / `HOUR` / `DAY` | Outbound safety budget ceilings | `6` / `60` / `300` |
| `ACTIVE_HOURS_START` / `ACTIVE_HOURS_END` | Local active window (`0–23`); empty runs 24/7 | — |
| `DASHBOARD_ENABLED` / `DASHBOARD_PORT` | Enable embedded web telemetry UI | `false` / `8765` |

### 3. Run Modes

| Command | Purpose |
| --- | --- |
| `python start_bot.py --mode check` | Validate Python environment, Chrome binary, configs, and proxy connectivity |
| `python start_bot.py --mode dashboard` | Launch Web Telemetry Console & AI Sandbox at `http://127.0.0.1:8765` |
| `python start_bot.py --mode cli` | Interactive terminal chat against `InstaBot` & SQLite memory |
| `python start_bot.py --mode run --dashboard` | Run live Instagram Direct automation alongside the telemetry UI |

Helper scripts [`run_bot.bat`](run_bot.bat) and [`run_bot.sh`](run_bot.sh) forward CLI flags automatically (e.g., `./run_bot.sh --mode check`).

---

## Docker

```bash
cp .env.example .env
docker compose up -d --build
```

The container runs as a non-root user (`instachat`), mounts `./data` for persistent profiles/databases/logs, and exposes a health check at `GET /health`.

---

## Development & Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest -v
```

---

## Security & Responsible Use

- See [SECURITY.md](SECURITY.md) for vulnerability reporting and credential handling practices.
- Intended for educational research and personal automation workflows. Respect Instagram's Terms of Service and avoid unsolicited bulk messaging.
- Licensed under the [MIT License](LICENSE).
