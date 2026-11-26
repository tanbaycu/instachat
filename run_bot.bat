@echo off
title InstaChat v2.0
echo.
echo ================================================
echo          INSTACHAT v2.0 LAUNCHER
echo ================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
) else (
    set PYTHON_CMD=python
)

%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+
    pause
    exit /b 1
)

echo [INFO] Running with %PYTHON_CMD%
%PYTHON_CMD% start_bot.py %*
set EXIT_CODE=%errorlevel%

echo.
echo ================================================
echo Exited with code %EXIT_CODE%
exit /b %EXIT_CODE%
