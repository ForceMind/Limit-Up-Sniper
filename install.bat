@echo off
setlocal

echo =========================================
echo   Limit-Up Sniper Windows Installer
echo =========================================

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

:: 2. Create Virtual Environment
if not exist "venv" (
    echo [1/3] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/3] Virtual environment already exists.
)

:: 3. Install Dependencies
echo [2/3] Installing dependencies...
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

:: 4. Setup API Key
echo [3/3] Configuring API Key...
if not exist "config.bat" (
    set /p API_KEY="Enter your Deepseek API Key: "
    echo set DEEPSEEK_API_KEY=%API_KEY%> config.bat
    echo Configuration saved to config.bat
) else (
    echo config.bat already exists. Skipping configuration.
)

echo.
echo =========================================
echo   Installation Complete!
echo =========================================
echo To start the application, run: run.bat
echo.
pause
