"""
오디오 캡처 모듈 (core/audio_capture.py)
Windows WASAPI Loopback을 통해 기본 스피커 출력(Zoom 소리)을 백그라운드에서 실시간 캡처합니다.
"""

import os
import sys
import ctypes.util
import math
import queue
import threading
import time
import warnings
import numpy as np
from scipy.signal import resample_poly

# Windows 필수 System32 및 ole32.dll 라이브러리 검색 경로 강제 복구
if sys.platform.startswith("win"):
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if os.path.isdir(system32):
        current_path = os.environ.get("PATH", "")
        if system32.lower() not in current_path.lower():
            os.environ["PATH"] = system32 + os.path.pathsep + current_path
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(system32)
            except Exception:
                pass

    _orig_find_library = ctypes.util.find_library
    def _patched_find_library(name):
        res = _orig_find_library(name)
        if res is not None:
            return res
        for ext in (".dll", ""):
            candidate = os.path.join(system32, f"{name}{ext}")
            if os.path.isfile(candidate):
                return candidate
        return None
    ctypes.util.find_library = _patched_find_library

try:
    import soundcard as sc
    # Windows WASAPI 버퍼 지터로 인한 비치명적 경고 숨김 처리
    if hasattr(sc, "SoundcardRuntimeWarning"):
        warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)
except ImportError:
    sc = None


class AudioCaptureThread(threading.Thread):
    """
    Windows 기본 출력 장치(스피커/헤드폰) 소리를 수집하여
    16kHz 단일 채널(Mono) 부동소수점(float32) numpy 배열로 변환 후 큐에 전달합니다.
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        stop_event: threading.Event,
        target_rate: int = 16000,
        chunk_sec: float = 8.0,
    ):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.stop_event = stop_event
        self.target_rate = target_rate
        self.chunk_sec = chunk_sec
        self.device_name = "알 수 없음"

    def run(self):
        if sc is None:
            print("[오류] soundcard 라이브러리가 설치되지 않았습니다. pip install soundcard를 실행하세요.")
            return

        try:
            try:
                default_speaker = sc.default_speaker()
            except Exception:
                default_speaker = None

            if default_speaker is None:
                speakers = sc.all_speakers()
                if speakers:
                    default_speaker = speakers[0]
                else:
                    raise RuntimeError("연결된 오디오 출력 장치(스피커/헤드폰)를 찾을 수 없습니다.")

            self.device_name = default_speaker.name
            print(f"[오디오 캡처] 기본 출력 장치 감지: {self.device_name}")

            # Windows Loopback 마이크 장치 획득
            loopback_mic = None
            try:
                loopback_mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
            except Exception:
                pass

            if loopback_mic is None:
                mics = sc.all_microphones(include_loopback=True)
                loopback_mics = [m for m in mics if getattr(m, 'isloopback', False)]
                if loopback_mics:
                    loopback_mic = loopback_mics[0]
                else:
                    raise RuntimeError("Windows WASAPI Loopback 오디오 장치를 찾을 수 없습니다. (스피커 또는 이어폰 연결을 확인하세요)")
        except Exception as e:
            print(f"[오류] 기본 오디오 Loopback 장치를 찾을 수 없습니다: {e}")
            return

        # Windows WASAPI 기본 샘플레이트 (일반적으로 48000Hz)
        native_rate = 48000
        target_frames = int(native_rate * self.chunk_sec)
        # WASAPI 버퍼 오버플로우 방지를 위해 0.5초 단위로 부드럽게 버퍼 비우기
        sub_frames = int(native_rate * 0.5)

        # 리샘플링 분수 비율 계산 (native_rate -> target_rate)
        gcd_val = math.gcd(self.target_rate, native_rate)
        up_factor = self.target_rate // gcd_val
        down_factor = native_rate // gcd_val

        try:
            with loopback_mic.recorder(samplerate=native_rate) as rec:
                print(f"[오디오 캡처] 실시간 Loopback 스트리밍 시작 ({self.chunk_sec}초 단위)...")
                accumulated_blocks = []
                total_frames = 0

                while not self.stop_event.is_set():
                    # 0.5초 단위로 즉시 캡처하여 버퍼 지연 차단
                    block = rec.record(numframes=sub_frames)
                    accumulated_blocks.append(block)
                    total_frames += len(block)

                    # 설정된 청크 시간(예: 8초)에 도달하면 결합하여 STT 큐로 전송
                    if total_frames >= target_frames:
                        combined = np.concatenate(accumulated_blocks, axis=0)
                        accumulated_blocks.clear()
                        total_frames = 0

                        # 1. 다채널(Stereo) -> 모노(Mono) 변환
                        if combined.ndim > 1:
                            mono = np.mean(combined, axis=1).astype(np.float32)
                        else:
                            mono = combined.astype(np.float32)

                        # 2. 16kHz로 리샘플링
                        if up_factor != down_factor:
                            resampled = resample_poly(mono, up_factor, down_factor).astype(np.float32)
                        else:
                            resampled = mono

                        # 3. 큐에 전달
                        self.audio_queue.put(resampled)

                # 종료 시점에 남아 있는 잔여 버퍼(0.5초~7.5초)도 STT 큐로 전달
                if accumulated_blocks:
                    combined = np.concatenate(accumulated_blocks, axis=0)
                    if combined.ndim > 1:
                        mono = np.mean(combined, axis=1).astype(np.float32)
                    else:
                        mono = combined.astype(np.float32)
                    if up_factor != down_factor:
                        resampled = resample_poly(mono, up_factor, down_factor).astype(np.float32)
                    else:
                        resampled = mono
                    self.audio_queue.put(resampled)

        except Exception as e:
            if not self.stop_event.is_set():
                print(f"[오디오 캡처 오류] {e}")
