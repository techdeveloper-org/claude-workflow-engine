@echo off
REM Selective Sync Script for Claude Workflow Engine Repository (Windows)
REM Downloads and syncs only claude-workflow-engine components
REM
REM PURPOSE: Quick sync for claude-workflow-engine updates
REM This is a convenience wrapper around hook-downloader.py sync-claude-workflow-engine
REM
REM USAGE:
REM   sync-workflow-engine.bat
REM   sync-workflow-engine
REM
REM What it syncs:
REM   - All scripts from claude-workflow-engine
REM   - All policies from claude-workflow-engine
REM   - Dashboard app (src, templates, static)
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
python "%HOOK_DOWNLOADER%" sync-claude-workflow-engine
exit /b %ERRORLEVEL%
