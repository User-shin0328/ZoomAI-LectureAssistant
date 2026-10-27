﻿[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Zoom AI Lecture Assistant - 완전 삭제 마법사"

function Write-Step {
    param([string]$Num, [string]$Title)
    Write-Host "`n[$Num] $Title" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Msg)
    Write-Host " [V] $Msg" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Msg)
    Write-Host " [!] $Msg" -ForegroundColor Yellow
}

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

Clear-Host
Write-Host "======================================================================" -ForegroundColor Red
Write-Host "   🗑️  Zoom 강의 AI 비서 [완전 삭제 및 클린 제거 마법사]" -ForegroundColor White
Write-Host "   - 가상환경(.venv), 바탕화면 바로가기, 다운로드된 모델 캐시," -ForegroundColor Gray
Write-Host "     Docker 컨테이너를 시스템에서 깔끔하게 제거합니다." -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Red

Write-Host "`n정말로 모든 구성 요소를 삭제하시겠습니까?" -ForegroundColor Yellow
$choice = Read-Host "계속 진행하려면 'Y'를 입력하세요 (취소하려면 아무 키나 입력)"
if ($choice -ne "Y" -and $choice -ne "y") {
    Write-Host "`n삭제가 취소되었습니다. 프로그램을 종료합니다." -ForegroundColor Gray
    exit 0
}

# -------------------------------------------------------------------------
# Step 1: 실행 중인 프로세스 및 도커 컨테이너 종료
# -------------------------------------------------------------------------
Write-Step "1/5" "실행 중인 관련 프로세스 및 도커 컨테이너 정리"

# 도커 컨테이너 정리
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "  도커 컨테이너(lecture-ai-ollama)를 정리합니다..." -ForegroundColor Gray
    & docker stop lecture-ai-ollama 2>$null
    & docker rm lecture-ai-ollama 2>$null
    & docker volume rm lecture_ai_ollama_models 2>$null
}

# 파이썬 잔류 프로세스 종료
$procs = Get-Process -Name "python" -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    try {
        if ($p.Path -like "**") {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
Write-Success "프로세스 및 도커 정리 완료"

# -------------------------------------------------------------------------
# Step 2: 바탕화면 바로가기 및 사용법 파일 삭제
# -------------------------------------------------------------------------
Write-Step "2/5" "바탕화면 바로가기 및 안내 파일 삭제"

$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutFiles = @(
    (Join-Path $DesktopPath "Zoom AI Lecture Assistant.lnk"),
    (Join-Path $DesktopPath "Zoom_AI_비서_사용법.txt"),
    (Join-Path $DesktopPath "Zoom 실시간 강의 AI 요약 비서.lnk")
)

foreach ($file in $ShortcutFiles) {
    if (Test-Path $file) {
        Remove-Item -Path $file -Force -ErrorAction SilentlyContinue
        Write-Host "  -> 삭제됨: $file" -ForegroundColor Gray
    }
}
Write-Success "바탕화면 파일 삭제 완료"

# -------------------------------------------------------------------------
# Step 3: 파이썬 가상환경(.venv) 삭제
# -------------------------------------------------------------------------
Write-Step "3/5" "파이썬 가상환경(.venv) 제거 (수백 MB 용량 확보)"

$VenvDir = Join-Path $RootDir ".venv"
if (Test-Path $VenvDir) {
    Write-Host "  가상환경 폴더(.venv)를 삭제하고 있습니다..." -ForegroundColor Gray
    Remove-Item -Path $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Success "가상환경 삭제 완료"
} else {
    Write-Success "가상환경 폴더가 이미 없습니다."
}

# -------------------------------------------------------------------------
# Step 4: Whisper 음성 인식 모델 캐시 삭제 (약 486MB 확보)
# -------------------------------------------------------------------------
Write-Step "4/5" "Whisper 음성 모델 캐시 파일 삭제"

$HfWhisperCache = Join-Path $env:USERPROFILE ".cache\huggingface\hub\models--Systran--faster-whisper-small"
if (Test-Path $HfWhisperCache) {
    Write-Host "  다운로드되었던 Whisper 모델 가중치 캐시(약 486MB)를 삭제합니다..." -ForegroundColor Gray
    Remove-Item -Path $HfWhisperCache -Recurse -Force -ErrorAction SilentlyContinue
    Write-Success "Whisper 모델 캐시 삭제 완료"
} else {
    Write-Success "삭제할 Whisper 모델 캐시가 없습니다."
}

# -------------------------------------------------------------------------
# Step 5: 강의 노트 폴더 삭제 여부 확인
# -------------------------------------------------------------------------
Write-Step "5/5" "기록된 강의 노트(notes/) 폴더 정리"

$NotesDir = Join-Path $RootDir "notes"
if (Test-Path $NotesDir) {
    Write-Host "`n그동안 기록된 강의 노트 폴더($NotesDir)도 함께 삭제하시겠습니까?" -ForegroundColor Yellow
    $noteChoice = Read-Host "강의 노트까지 모두 지우려면 'Y' 입력 (보관하려면 Enter)"
    if ($noteChoice -eq "Y" -or $noteChoice -eq "y") {
        Remove-Item -Path $NotesDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Success "강의 노트(notes/) 폴더 삭제 완료"
    } else {
        Write-Host "  -> 강의 노트(notes/) 폴더는 보관됩니다." -ForegroundColor Gray
    }
}

# -------------------------------------------------------------------------
# 완료 안내
# -------------------------------------------------------------------------
Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "   🎉 모든 설치 파일 및 캐시가 깔끔하게 삭제되었습니다!" -ForegroundColor Green
Write-Host "   - 필요 시 언제든 install.bat을 더블 클릭하면 다시 원클릭 설치됩니다." -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "`n창을 닫으려면 아무 키나 누르세요.`n" -ForegroundColor White
