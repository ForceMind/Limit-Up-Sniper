@echo off
setlocal

echo =========================================
echo   Limit-Up Sniper Updater
echo =========================================

:: 1. Git Pull
echo [1/2] Pulling latest code...
git pull
if %errorlevel% neq 0 (
    echo [Error] Git pull failed. Please check your internet connection or git status.
    pause
    exit /b 1
)

:: 2. Update Dependencies
echo [2/2] Updating dependencies...
if exist "venv" (
    call venv\Scripts\activate
    pip install -r requirements.txt
) else (
    echo [Warning] Virtual environment not found. Skipping dependency update.
)

echo.
echo Update Complete!
pause
