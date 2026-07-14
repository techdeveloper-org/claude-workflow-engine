@echo off
REM Stop Claude Workflow Engine Server

setlocal

set PROJECT_DIR=%~dp0..
set PID_FILE=%PROJECT_DIR%\data\.server.pid

echo.
echo ========================================
echo   Stopping Claude Workflow Engine Server
echo ========================================
echo.

REM Kill Python process running Flask
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Claude Workflow Engine*" 2>nul

REM Alternative: Kill all Python processes (careful!)
REM taskkill /F /IM python.exe 2>nul

REM Remove PID file
if exist "%PID_FILE%" (
    del "%PID_FILE%"
    echo [OK] Server stopped
) else (
    echo [INFO] No PID file found - server may not be running
)

echo.
pause

endlocal
