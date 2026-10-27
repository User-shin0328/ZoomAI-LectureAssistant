@echo off
setlocal

REM 0. Windows 핵심 시스템 디렉터리(System32) PATH 강제 복구
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0\;%LOCALAPPDATA%\Programs\Ollama;%PATH%"

chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Zoom Lecture AI - Self-Healing Repair Wizard
cd /d "%~dp0"

echo ========================================================
echo    Zoom Lecture AI - Self-Healing Repair Wizard
echo ========================================================
echo.
echo Launching automated repair and diagnosis...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\repair.ps1"

if errorlevel 1 (
    echo.
    echo [ERROR] Repair encountered an unexpected issue.
    pause
    exit /b 1
)

echo.
echo Press any key to finish...
pause > nul
