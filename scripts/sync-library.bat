@echo off
REM Selective Sync Script for Claude Global Library (Windows)
REM Downloads and syncs only skills and agents
REM
REM PURPOSE: Quick sync for claude-global-library updates
REM This is a convenience wrapper around hook-downloader.py sync-claude-global-library
REM
REM USAGE:
REM   sync-library.bat
REM   sync-library
REM
REM What it syncs:
REM   - All skills from claude-global-library
REM   - All agents from claude-global-library
REM
REM Version: 1.0.0

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "HOOK_DOWNLOADER=%SCRIPT_DIR%hook-downloader.py"

if not exist "%HOOK_DOWNLOADER%" (
    echo [ERROR] hook-downloader.py not found
    exit /b 1
)

REM Call hook-downloader with selective sync parameter
python "%HOOK_DOWNLOADER%" sync-claude-global-library
exit /b %ERRORLEVEL%
