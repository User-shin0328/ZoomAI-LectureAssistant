@echo off
setlocal

REM 0. Ensure System32 is in PATH
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0\;%LOCALAPPDATA%\Programs\Ollama;%PATH%"

chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Zoom Lecture AI - Complete Uninstaller
cd /d "%~dp0"

echo ========================================================
echo    Zoom Lecture AI Assistant - Complete Uninstaller
echo ========================================================
echo.
echo Launching cleanup wizard...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1"

if errorlevel 1 (
    echo.
    echo [ERROR] Cleanup encountered an unexpected issue.
    pause
    exit /b 1
)

echo.
pause
