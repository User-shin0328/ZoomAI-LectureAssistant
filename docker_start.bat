@echo off
title Start Lecture AI Ollama Docker Server
cd /d "%~dp0"

echo ========================================================
echo    Launching Ollama Server in Docker (24/7 Container)
echo ========================================================
echo.

docker compose up -d

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start Docker container. Ensure Docker Desktop is running.
    pause
    exit /b 1
)

echo.
echo [Ollama Docker] Pulling Qwen2.5 7B model inside container...
docker exec -it lecture-ai-ollama ollama pull qwen2.5:7b

echo.
echo ========================================================
echo  Docker Ollama container is now running 24/7 on port 11434!
echo ========================================================
pause
