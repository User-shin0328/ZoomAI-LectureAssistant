"""
STT 엔진 모듈 (core/stt_engine.py)
Faster-Whisper를 활용하여 수집된 16kHz 모노 오디오를 한국어 텍스트로 고속 변환합니다.
황금 밸런스 설정: CPU INT8 양자화 적용 (VRAM 고갈 방지)
"""

import os
# Windows Huggingface symlink 경고 및 OpenMP 라이브러리 충돌 방지
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class STTEngine:
    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ko",
        beam_size: int = 3,
        vad_filter: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.model = None

    def load_model(self):
        """Whisper 모델을 메모리에 로드합니다."""
        if WhisperModel is None:
            raise ImportError(
                "faster-whisper 라이브러리가 설치되지 않았습니다. pip install faster-whisper를 실행하세요."
            )

        try:
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=4,
            )
        except Exception:
            self.compute_type = "float32"
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=4,
            )

    def transcribe(self, audio: np.ndarray) -> str:
        """
        16kHz float32 오디오 배열을 전사하여 텍스트를 반환합니다.
        무음이거나 의미 있는 발화가 없으면 빈 문자열('')을 반환합니다.
        """
        if self.model is None:
            self.load_model()

        # 진폭이 너무 낮은 완전 무음 필터링 (불필요한 연산 방지)
        energy = np.mean(np.abs(audio))
        if energy < 1e-4:
            return ""

        try:
            segments, _ = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                vad_parameters=dict(min_silence_duration_ms=400),
            )
            text_parts = [s.text.strip() for s in segments if s.text.strip()]
            return " ".join(text_parts).strip()
        except Exception as e:
            print(f"[STT 전사 오류] {e}")
            return ""
