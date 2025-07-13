@echo off
title InstaChatBot
echo.
echo ================================================
echo          🤖 INSTACHATBOT LAUNCHER
echo ================================================
echo.

:: Kiểm tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python not found! Please install Python 3.8+
    pause
    exit /b 1
)

:: Chạy startup script
echo 🚀 Starting InstaChatBot...
echo.
python start_bot.py

:: Pause để xem kết quả
echo.
echo ================================================
echo Press any key to exit...
pause >nul 