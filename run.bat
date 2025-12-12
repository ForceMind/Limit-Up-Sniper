@echo off
setlocal

:: Clear Proxy (Fix for requests failing in some environments)
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=

:: Check if venv exists
if not exist "venv" (
    echo [Error] Virtual environment not found. Please run install.bat first.
    pause
    exit /b 1
)

:: Load Configuration
if exist "config.bat" (
    call config.bat
) else (
    echo [Warning] config.bat not found.
    set /p API_KEY="Enter your Deepseek API Key (or press Enter to skip): "
    if not "%API_KEY%"=="" (
        set DEEPSEEK_API_KEY=%API_KEY%
        echo set DEEPSEEK_API_KEY=%API_KEY%> config.bat
    )
)

:: Activate venv and run
call venv\Scripts\activate
echo Starting Limit-Up Sniper...
echo Access at: http://127.0.0.1:8000
python -m uvicorn app.main:app --reload --port 8000

pause
