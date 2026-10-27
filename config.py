"""
설정 파일 (config.py)
황금 밸런스 구성:
- STT: Faster-Whisper Small (CPU INT8)
- LLM: Ollama Qwen2.5 7B (GPU VRAM 가속)
"""

from pathlib import Path

# --- 오디오 캡처 설정 ---
TARGET_SAMPLE_RATE = 16000     # Whisper 표준 입력 샘플링 레이트 (16kHz)
CHUNK_DURATION_SEC = 8         # 실시간 자막 전사 주기 (초 단위: 7~10초 권장)
SUMMARY_INTERVAL_SEC = 180     # AI 구간 요약 주기 (초 단위: 180초 = 3분)

# --- STT (Faster-Whisper) 설정 ---
# VRAM 6GB 보호를 위해 Whisper는 CPU INT8로 고속 추론
WHISPER_MODEL = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_LANGUAGE = "ko"
WHISPER_BEAM_SIZE = 3
WHISPER_VAD_FILTER = True      # 무음 구간 자동 감지 및 제거

# --- LLM (Ollama) 설정 ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"     # 기본 모델
OLLAMA_TIMEOUT = 240           # CPU 추론 여유를 위해 타임아웃 240초(4분)로 확대

# --- 저장 경로 설정 ---
BASE_OUTPUT_DIR = Path(__file__).resolve().parent / "notes"
