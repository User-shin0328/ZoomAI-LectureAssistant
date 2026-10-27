@echo off
setlocal

set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0\;%LOCALAPPDATA%\Programs\Ollama;%PATH%"

chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Zoom Lecture AI Assistant
cd /d "%~dp0"

REM 1. Check virtualenv
if exist ".venv\Scripts\python.exe" goto CHECK_OLLAMA

echo [1/3] Initializing virtual environment...
set "PY_CMD=py"
where py >nul 2>&1 || set "PY_CMD=python"
where %PY_CMD% >nul 2>&1 || set "PY_CMD=python3"
where %PY_CMD% >nul 2>&1 || goto NO_PYTHON

echo Creating virtual environment using %PY_CMD%...
%PY_CMD% -m venv .venv || goto VENV_FAIL

echo [2/3] Installing dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto PIP_FAIL
goto CHECK_OLLAMA

:NO_PYTHON
echo [ERROR] Python was not found on your system.
echo Please run install.bat to set up Python and all dependencies automatically.
pause
exit /b 1

:VENV_FAIL
echo [ERROR] Failed to create virtual environment.
pause
exit /b 1

:PIP_FAIL
echo [ERROR] Failed to install dependencies.
pause
exit /b 1

:CHECK_OLLAMA
netstat -ano | findstr /R ":11434.*LISTENING" >nul 2>&1
if not errorlevel 1 goto RUN_APP

curl.exe -s http://127.0.0.1:11434/ >nul 2>&1
if not errorlevel 1 goto RUN_APP

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    start "" /B "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve >nul 2>&1
    ping 127.0.0.1 -n 3 >nul
    goto RUN_APP
)

where ollama >nul 2>&1
if not errorlevel 1 (
    start "" /B ollama serve >nul 2>&1
    ping 127.0.0.1 -n 3 >nul
    goto RUN_APP
)

:RUN_APP
cls
.venv\Scripts\python.exe main.py

if errorlevel 1 (
    echo.
    echo ========================================================
    echo  Execution finished with an error.
    echo  Tip: If installation was interrupted, double-click repair.bat to auto-repair!
    echo ========================================================
    pause
)
