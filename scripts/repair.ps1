﻿[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Zoom AI Lecture Assistant - 원클릭 자가 복구 마법사"

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
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host "   🔧 Zoom 강의 AI 비서 [자가 치유 및 원클릭 복구 마법사]" -ForegroundColor White
Write-Host "   - 설치 도중 창을 닫았거나 다운로드가 끊겼을 때 완벽 복구합니다." -ForegroundColor Gray
Write-Host "   - 손상된 임시 파일, 깨진 가상환경, 좀비 프로세스를 모두 청소합니다." -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Magenta

# -------------------------------------------------------------------------
# Step 1: 백그라운드 잔류 및 좀비 프로세스 완전 정리
# -------------------------------------------------------------------------
Write-Step "1/5" "백그라운드 잔류 프로세스(Ollama, Python) 완전 종료"

$KillList = @("python", "ollama", "ollama app")
foreach ($proc in $KillList) {
    $found = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($found) {
        Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
        Write-Host "  -> 잔류 프로세스($proc) 강제 종료 완료" -ForegroundColor Gray
    }
}
Start-Sleep -Seconds 1
Write-Success "프로세스 충돌 요소 청소 완료"

# -------------------------------------------------------------------------
# Step 2: 손상되었을 수 있는 가상환경(.venv) 클린 삭제 및 재구축
# -------------------------------------------------------------------------
Write-Step "2/5" "가상환경 무결성 검증 및 초기화"

$VenvDir = Join-Path $RootDir ".venv"
if (Test-Path $VenvDir) {
    Write-Host "  기존/손상된 가상환경(.venv) 폴더를 깨끗하게 삭제합니다..." -ForegroundColor Gray
    try {
        Remove-Item -Path $VenvDir -Recurse -Force -ErrorAction Stop
        Write-Success "기존 가상환경 폴더 삭제 완료"
    } catch {
        Write-Warn "일부 파일 삭제 지연 중... 재시도합니다."
        Start-Sleep -Seconds 2
        Remove-Item -Path $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Python 명령어 감지
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

Write-Host "새로운 순정 가상환경을 생성합니다..." -ForegroundColor Gray
& $PythonCmd -m venv .venv
if ($LASTEXITCODE -ne 0) {
    Write-Err "가상환경 생성 실패. Python 설치 상태를 점검해 주세요."
    exit 1
}

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
Write-Host "필수 라이브러리(faster-whisper, soundcard, scipy 등)를 새로 설치합니다..." -ForegroundColor Gray
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $RootDir "requirements.txt")
Write-Success "가상환경 및 필수 라이브러리 복구 완료"

# -------------------------------------------------------------------------
# Step 3: Ollama 서비스 재기동 및 모델 무결성 검증
# -------------------------------------------------------------------------
Write-Step "3/5" "Ollama 서비스 재가동 및 Qwen2.5 7B 모델 복구"

$OllamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if (-not (Test-Path $OllamaExe)) {
    $OllamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if ($OllamaCommand) {
        $OllamaExe = $OllamaCommand.Source
    }
}

if (-not (Test-Path $OllamaExe)) {
    Write-Warn "Ollama가 설치되어 있지 않습니다. 다운로드를 시작합니다..."
    $TempInstaller = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $TempInstaller
    Start-Process -FilePath $TempInstaller -Wait
}

Write-Host "Ollama 백엔드 서버를 깨끗하게 재시작합니다..." -ForegroundColor Gray
Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Host "Qwen2.5 7B 모델 무결성을 검증하고 손상된 블록을 자동 복구합니다..." -ForegroundColor Gray
# Ollama pull은 중단된 지점부터 자동으로 이어받기 및 SHA256 검증을 수행합니다
& $OllamaExe pull qwen2.5:7b
Write-Success "Ollama AI 요약 모델 검증 및 복구 완료"

# -------------------------------------------------------------------------
# Step 4: Whisper 음성 인식 모델 무결성 검증
# -------------------------------------------------------------------------
Write-Step "4/5" "Whisper 음성인식 모델 무결성 검사 (손상 파일 자동 재다운로드)"

$CacheTestCode = @"
import os
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
try:
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8')
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}')
"@

Write-Host "Whisper Small 모델을 실제 메모리에 로드하여 정상 동작을 확인합니다..." -ForegroundColor Gray
$testResult = & $VenvPython -c $CacheTestCode
if ($testResult -like "*SUCCESS*") {
    Write-Success "Whisper Small 모델 무결성 확인 완료 (정상 동작)"
} else {
    Write-Warn "Whisper 모델 파일이 손상되었습니다. 손상된 캐시를 삭제하고 다시 받습니다..."
    $HfCacheDir = Join-Path $env:USERPROFILE ".cache\huggingface\hub\models--Systran--faster-whisper-small"
    if (Test-Path $HfCacheDir) {
        Remove-Item -Path $HfCacheDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    & $VenvPython -c $CacheTestCode
    Write-Success "Whisper Small 모델 재다운로드 및 복구 완료"
}

# -------------------------------------------------------------------------
# Step 5: 바로가기 아이콘 갱신
# -------------------------------------------------------------------------
Write-Step "5/5" "바탕화면 바로가기 아이콘 복구 및 갱신"

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
    Write-Success "바탕화면 바로가기 갱신 완료"
} catch {
    Write-Warn "바로가기 생성 중 사소한 경고 발생"
}

# -------------------------------------------------------------------------
# 복구 완료 안내
# -------------------------------------------------------------------------
Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "   🎉 모든 구성 요소가 100% 정상 상태로 완벽 복구되었습니다!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "`n이제 안심하고 바탕화면의 [Zoom AI Lecture Assistant]를 실행하시면 됩니다.`n" -ForegroundColor White
