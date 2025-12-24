@echo off
setlocal EnableDelayedExpansion

echo =========================================
echo   Limit-Up Sniper Updater (Windows)
echo =========================================

:: 1. Backup Data
echo [1/3] Backing up data...
if exist "data" (
    if exist "._data_backup" rd /s /q "._data_backup"
    xcopy /E /I /Q /Y "data" "._data_backup" >nul
    echo Data backed up to ._data_backup
)

:: 2. Git Pull
echo [2/3] Pulling latest code...
git config --global --add safe.directory "*"
git pull
if %errorlevel% neq 0 (
    echo.
    echo [!] Git pull failed. Likely due to local data changes.
    echo.
    echo Options:
    echo  1. Force update (Discard code changes, KEEP data) - Recommended
    echo  2. Cancel
    echo.
    set /p CHOICE="Enter choice (1/2): "
    
    if "!CHOICE!"=="1" (
        echo.
        echo Force updating...
        for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
        git fetch --all
        git reset --hard origin/!BRANCH!
        
        :: Restore Data
        if exist "._data_backup" (
            echo Restoring data...
            xcopy /E /I /Q /Y "._data_backup" "data" >nul
        )
    ) else (
        echo.
        echo Cancelled. Restoring data...
        if exist "._data_backup" (
            xcopy /E /I /Q /Y "._data_backup" "data" >nul
            rd /s /q "._data_backup"
        )
        pause
        exit /b 1
    )
) else (
    :: Normal pull success, still restore data to ensure we keep local configs if they were overwritten
    if exist "._data_backup" (
        echo Restoring data...
        xcopy /E /I /Q /Y "._data_backup" "data" >nul
    )
)

:: Cleanup backup
if exist "._data_backup" rd /s /q "._data_backup"

:: 3. Update Dependencies
echo [3/3] Updating dependencies...
if exist "venv" (
    call venv\Scripts\activate
    pip install -r requirements.txt
) else (
    echo [Warning] Virtual environment not found.
)

echo.
echo Update Complete!
pause
