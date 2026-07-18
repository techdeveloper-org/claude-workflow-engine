@echo off
REM Claude Workflow Engine Startup Script for Windows
REM Starts the Flask server in background

setlocal

set PROJECT_DIR=%~dp0..
set LOG_DIR=%PROJECT_DIR%\logs
set LOG_FILE=%LOG_DIR%\server.log
set PID_FILE=%PROJECT_DIR%\data\.server.pid

REM Create logs directory if not exists
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Check if already running
if exist "%PID_FILE%" (
    echo [INFO] Claude Workflow Engine may already be running
    echo [INFO] PID file exists: %PID_FILE%
    echo [INFO] If server is not running, delete this file and try again
    exit /b 0
)

echo.
echo ========================================
echo   Starting Claude Workflow Engine Server
echo ========================================
echo.
echo Project: %PROJECT_DIR%
echo Log File: %LOG_FILE%
echo URL: http://localhost:5000
echo.

REM Start Python server in background
cd /d "%PROJECT_DIR%"
start /B python scripts\start-server.py >> "%LOG_FILE%" 2>&1

REM Save PID (approximation for Windows)
echo %date% %time% > "%PID_FILE%"

echo [OK] Server started successfully!
echo [OK] Access dashboard at: http://localhost:5000
echo [OK] Logs: %LOG_FILE%
echo.
echo Press any key to exit (server will continue running)...
pause > nul

endlocal
