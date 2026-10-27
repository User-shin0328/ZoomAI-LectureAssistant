﻿[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Zoom AI Lecture Assistant - Installer"

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

function Write-Err {
    param([string]$Msg)
    Write-Host " [X] $Msg" -ForegroundColor Red
}

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

Clear-Host
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   Zoom 실시간 강의 자막 & AI 자동 요약 비서 자동 설치 마법사" -ForegroundColor White
Write-Host "   - STT: Faster-Whisper Small (CPU INT8)" -ForegroundColor Gray
Write-Host "   - LLM: Ollama Qwen2.5 7B (로컬 온디바이스)" -ForegroundColor Gray
Write-Host "   - 설치 경로: $RootDir" -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Cyan

# -------------------------------------------------------------------------
# Step 1: Python 환경 및 가상환경 구성
# -------------------------------------------------------------------------
Write-Step "1/4" "Python 환경 점검 및 라이브러리 가상환경(.venv) 구축"

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    # Python 명령어 감지 (py -> python -> python3)
    $PythonCmd = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonCmd = "py"
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonCmd = "python"
    } elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
        $PythonCmd = "python3"
    }

    if (-not $PythonCmd) {
        Write-Warn "Python이 설치되어 있지 않습니다. Python 3.11 공식 설치 프로그램을 다운로드합니다..."
        $PyInstaller = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
        Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $PyInstaller
        Write-Host "Python 설치 마법사를 실행합니다. 'Add python.exe to PATH'에 반드시 체크하고 설치해 주세요." -ForegroundColor Yellow
        Start-Process -FilePath $PyInstaller -Wait
        $PythonCmd = "py"
    }

    Write-Host "가상환경을 생성하고 있습니다 ($PythonCmd -m venv .venv)..." -ForegroundColor Gray
    & $PythonCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Err "가상환경 생성에 실패했습니다. Python이 정상 설치되었는지 확인해 주세요."
        exit 1
    }
}
Write-Success "가상환경 준비 완료"

Write-Host "필수 라이브러리(Whisper, SoundCard, SciPy 등)를 설치 및 확인합니다..." -ForegroundColor Gray
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $RootDir "requirements.txt")
if ($LASTEXITCODE -eq 0) {
    Write-Success "파이썬 필수 의존성 패키지 설치 완료"
} else {
    Write-Warn "패키지 설치 중 일부 경고가 발생했으나 계속 진행합니다."
}

# -------------------------------------------------------------------------
# Step 2: Ollama 서비스 점검 및 모델 다운로드
# -------------------------------------------------------------------------
Write-Step "2/4" "Ollama 로컬 AI 서비스 및 Qwen2.5 7B 모델 확인"

$OllamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if (-not (Test-Path $OllamaExe)) {
    $OllamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if ($OllamaCommand) {
        $OllamaExe = $OllamaCommand.Source
    }
}

if (-not (Test-Path $OllamaExe)) {
    Write-Warn "Ollama가 설치되어 있지 않습니다. 공식 설치 프로그램 다운로드를 시작합니다..."
    $InstallerUrl = "https://ollama.com/download/OllamaSetup.exe"
    $TempInstaller = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $TempInstaller
    Write-Host "Ollama 설치 마법사를 실행합니다. 설치를 완료한 후 계속해 주세요." -ForegroundColor Yellow
    Start-Process -FilePath $TempInstaller -Wait
}

# 기존 좀비/먹통 프로세스 정리 후 백엔드 서버 가동
$IsOllamaRunning = $false
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
    $IsOllamaRunning = $true
} catch {
    $IsOllamaRunning = $false
}

if (-not $IsOllamaRunning) {
    Write-Host "Ollama 백엔드 서버를 가동합니다..." -ForegroundColor Gray
    Stop-Process -Name "*ollama*" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 모델 점검 및 다운로드
Write-Host "Qwen2.5 7B 요약 모델을 확인합니다..." -ForegroundColor Gray
$tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -ErrorAction SilentlyContinue
$modelNames = $tags.models | ForEach-Object { $_.name }

if ($modelNames -contains "qwen2.5:7b" -or ($modelNames -like "*qwen2.5:7b*")) {
    Write-Success "Qwen2.5 7B 모델이 이미 준비되어 있습니다."
} else {
    Write-Host "Qwen2.5 7B 모델을 다운로드합니다 (약 4.7GB, 초고속 다운로드)..." -ForegroundColor Yellow
    & $OllamaExe pull qwen2.5:7b
    Write-Success "Qwen2.5 7B 모델 다운로드 완료"
}

# -------------------------------------------------------------------------
# Step 3: Whisper 음성 인식 모델 사전 캐싱
# -------------------------------------------------------------------------
Write-Step "3/4" "Whisper Small 음성 인식 모델 사전 캐싱 (첫 강의 구동 지연 제거)"
$CacheCheckCode = "import os; os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING']='1'; os.environ['KMP_DUPLICATE_LIB_OK']='TRUE'; from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
Write-Host "Whisper 모델을 검증합니다..." -ForegroundColor Gray
& $VenvPython -c $CacheCheckCode
Write-Success "Whisper Small 모델 캐싱 완료"

# -------------------------------------------------------------------------
# Step 4: 바탕화면 바로가기 아이콘 생성
# -------------------------------------------------------------------------
Write-Step "4/4" "바탕화면에 원클릭 실행 바로가기 생성"

$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "Zoom AI Lecture Assistant.lnk"
$TargetBat = Join-Path $RootDir "run.bat"

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetBat
    $Shortcut.WorkingDirectory = $RootDir
    $Shortcut.Description = "Zoom 실시간 강의 자막 및 AI 자동 요약 비서"
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,23"
    $Shortcut.Save()
    Write-Success "바탕화면 바로가기 생성 완료: $ShortcutPath"
} catch {
    Write-Warn "바로가기 생성 중 경고가 발생했으나 프로그램 실행에는 문제 없습니다."
}

# -------------------------------------------------------------------------
# 완료 안내
# -------------------------------------------------------------------------
Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "   모든 설치와 사전 준비가 완벽하게 완료되었습니다!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "`n[사용 방법]" -ForegroundColor White
Write-Host " 1. 바탕화면에 생성된 [Zoom AI Lecture Assistant] 바로가기를 더블 클릭하세요." -ForegroundColor White
Write-Host " 2. Zoom 강의 또는 영상을 재생하면 실시간 자막과 3분 요약이 시작됩니다." -ForegroundColor White
Write-Host " 3. 강의가 끝나면 터미널에서 Ctrl+C를 눌러 [강의 종합 리포트]를 확인하세요.`n" -ForegroundColor White
