# 🎓 Zoom 실시간 강의 자막 & AI 자동 요약 비서 (Local Lecture AI)

> **황금 밸런스 구성:**  
> - **음성 인식(STT):** `faster-whisper` (Small 모델, CPU INT8 양자화)  
> - **인공지능(LLM):** `Ollama` (`qwen2.5:7b`, NVIDIA GPU VRAM 6GB 가속)  
> - **오디오 수집:** Windows WASAPI Loopback (`soundcard`) — Zoom 봇 없이 PC 출력 소리 수집  
> - **비용 & 네트워크:** 100% 로컬 온디바이스 구동 (외부 유료 API 없음, 오프라인 작동)

---

## 🌟 기존 코드 대비 주요 보완 사항

1. **마지막 미요약 구간 누락 방지:**
   - 강의 도중 언제든 `Ctrl+C`로 종료해도, **종료 직전 큐에 남은 오디오를 모두 비우고 미요약 텍스트까지 안전하게 요약**하여 저장합니다.
2. **전체 강의 종합 분석 리포트 자동 생성:**
   - 3분 단위 구간 요약뿐만 아니라, 강의 종료 시 군더더기 없이 **`[1. 핵심 요약 - 2. 강의 세부 내용 정리]`**로만 구성된 깔끔한 최종 강의 노트를 추가 생성합니다.
3. **무음 구간 및 CPU 부하 최적화:**
   - Whisper의 VAD(Voice Activity Detection) 필터와 진폭 감지 로직을 강화하여 불필요한 무음 구간 전사 연산을 차단하고 CPU 점유율을 대폭 낮췄습니다.
4. **체계적인 세션 폴더 관리:**
   - 매 강의 실행 시 `notes/lecture_YYYYMMDD_HHMMSS/` 디렉터리가 자동 생성되며, 파일이 덮어씌워지지 않고 개별 강의별로 영구 보관됩니다.
   - `transcript.txt`: 타임스탬프(`[HH:MM:SS]`)가 포함된 전체 실시간 자막
   - `summary.md`: 3분 주기 롤링 요약 노트
   - `final_lecture_report.md`: 복습/시험 대비용 전체 종합 리포트

---

## 🚀 빠른 시작 가이드 (Windows)

### 1단계: Ollama 모델 준비
PowerShell을 열고 황금 밸런스 모델을 다운로드합니다:
```powershell
ollama pull qwen2.5:7b
```
*(만약 PC 용량이 부족하거나 더 가벼운 모델을 원하시면 `ollama pull qwen2.5:3b`도 자동 호환됩니다.)*

### 2단계: 실행 (원클릭 또는 수동)

#### 방법 A. 원클릭 실행
프로젝트 폴더 내 `run.bat` 파일을 더블 클릭하면 자동으로 가상환경 생성, 패키지 설치 및 프로그램 실행이 진행됩니다.

#### 방법 B. 터미널 수동 실행
```powershell
# 1. 가상환경 생성 및 활성화
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 필수 라이브러리 설치
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3. 프로그램 실행
python main.py
```

---

## ⚙️ 설정 커스터마이징 (`config.py`)

필요에 따라 `config.py`에서 설정을 간편하게 조정할 수 있습니다:

```python
# 실시간 자막 전사 주기 (기본값: 8초)
CHUNK_DURATION_SEC = 8

# AI 구간 요약 주기 (기본값: 180초 = 3분)
SUMMARY_INTERVAL_SEC = 180

# STT 모델 크기 ("tiny", "base", "small", "medium")
WHISPER_MODEL = "small"

# Ollama 요약 모델 ("qwen2.5:7b", "qwen2.5:3b", "qwen3:4b")
OLLAMA_MODEL = "qwen2.5:7b"
```

---

## 📁 생성 파일 구조

```text
notes/lecture_20261027_095500/
├── transcript.txt          # [00:01:15] 형태의 실시간 전체 자막 기록
├── summary.md              # 3분 단위 핵심 주제 / 주요 내용 / 키워드 요약
└── final_lecture_report.md # 강의 종료 시 자동 생성되는 전체 종합 학습 리포트
```
