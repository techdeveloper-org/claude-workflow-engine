@echo off
REM Verify+pull wrapper for the claude-global-library sibling (ADR-2 / FR-2, Windows)
REM
REM PURPOSE: Verify the sibling claude-global-library checkout exists next to
REM this repo, and optionally fast-forward it. Replaces the removed
REM hook-downloader.py-based sync flow -- there is nothing to "download" in a
REM sibling layout (the engine reads skills/agents/KG files directly from disk).
REM
REM USAGE:
REM   sync-library.bat           (verify only)
REM   sync-library.bat --pull    (verify + git pull --ff-only in the sibling)
REM
REM Exit codes:
REM   0 = verified (and, with --pull, up to date / fast-forwarded)
REM   2 = sibling not found
REM   3 = --pull failed (non-fast-forward or other git error)
REM
REM Version: 2.0.0

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "SYNC_LIBRARY=%SCRIPT_DIR%..\tools\sync-library.py"

if not exist "%SYNC_LIBRARY%" (
    echo [ERROR] sync-library.py not found at %SYNC_LIBRARY%
    exit /b 1
)

python "%SYNC_LIBRARY%" %*
exit /b %ERRORLEVEL%
