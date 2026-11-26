#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "================================================"
echo "         INSTACHAT v2.0 LAUNCHER"
echo "================================================"
echo ""

if [ -x ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "❌ Python 3.10+ not found!"
    exit 1
fi

echo "🚀 Running with $PYTHON_CMD"
exec "$PYTHON_CMD" start_bot.py "$@"
