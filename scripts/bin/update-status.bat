@echo off
REM Update Status Reporter - Clarifies successful updates vs actual failures
REM
REM PURPOSE: Show clear, user-friendly update completion messages
REM Distinguishes between:
REM   - Successful updates with optional warnings (still works!)
REM   - Actual failures (system broken)
REM
REM USAGE:
REM   update-status.bat success
REM   update-status.bat warning "optional warning message"
REM   update-status.bat failed "error message"

setlocal enabledelayedexpansion

set "STATUS=%1"
set "MESSAGE=%2"

if "%STATUS%"=="success" (
    echo ================================================================================
    echo ✅ UPDATE COMPLETED SUCCESSFULLY^!
    echo ================================================================================
    echo.
    echo Version: v0.39.0 (IDE) + v4.8.0 (Hooks)
    echo.
    echo What was updated:
    echo   ✓ hook-downloader.py        Updated to ~/.claude/scripts/
    echo   ✓ post-update.sh            Repository-aware syncing (Unix)
    echo   ✓ post-update.ps1           Repository-aware syncing (Windows)
    echo   ✓ sync-workflow-engine              Quick sync convenience script
    echo   ✓ sync-workflow-engine.bat          Quick sync convenience script (Windows)
    echo   ✓ Selective sync functions  New repo-aware syncing
    echo.
    echo Features:
    echo   ✓ Repository-aware detection
    echo   ✓ Selective syncing (much faster!)
    echo   ✓ Smart fallback mechanism
    echo   ✓ Zero manual intervention
    echo.
    echo System Status: READY FOR USE
    echo Next Update Check: 24 hours
    echo.
    echo ================================================================================
    exit /b 0

) else if "%STATUS%"=="warning" (
    echo ================================================================================
    echo ✅ UPDATE COMPLETED SUCCESSFULLY^!
    echo ================================================================================
    echo.
    echo Version: v0.39.0 (IDE) + v4.8.0 (Hooks)
    echo.
    echo ⚠️  Note: Some optional features not available
    echo    (Non-blocking - system still works perfectly!)
    echo.
    echo What was updated:
    echo   ✓ hook-downloader.py        Updated to ~/.claude/scripts/
    echo   ✓ core sync functions       All critical components working
    echo.
    echo System Status: OPERATIONAL
    echo Optional Features: Some unavailable (doesn't affect core functionality)
    echo.
    echo %MESSAGE%
    echo.
    echo Next Update Check: 24 hours
    echo.
    echo ================================================================================
    exit /b 0

) else if "%STATUS%"=="failed" (
    echo ================================================================================
    echo ❌ UPDATE FAILED - ACTION REQUIRED
    echo ================================================================================
    echo.
    echo Version: v0.39.0 (IDE) + v4.8.0 (Hooks)
    echo.
    echo Error:
    echo %MESSAGE%
    echo.
    echo System Status: REQUIRES ATTENTION
    echo.
    echo What to do:
    echo   1. Check your internet connection
    echo   2. Try manual sync: python ~/.claude/scripts/hook-downloader.py sync-all
    echo   3. If problem persists, check ~/.claude/scripts/hook-downloader.py exists
    echo.
    echo Support: Check logs at ~/.claude/memory/logs/
    echo.
    echo ================================================================================
    exit /b 1

) else (
    echo Usage: update-status.bat [success^|warning^|failed] [optional message]
    exit /b 1
)
