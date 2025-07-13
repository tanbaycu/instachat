#!/bin/bash

echo ""
echo "================================================"
echo "          🤖 INSTACHATBOT LAUNCHER"
echo "================================================"
echo ""

# Kiểm tra Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found! Please install Python 3.8+"
    exit 1
fi

# Chạy startup script
echo "🚀 Starting InstaChatBot..."
echo ""
python3 start_bot.py

# Pause để xem kết quả
echo ""
echo "================================================"
echo "Press Enter to exit..."
read 