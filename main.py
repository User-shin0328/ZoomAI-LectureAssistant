"""
Zoom 실시간 강의 자막 & 자동 요약 시스템 (main.py)
황금 밸런스 구성:
- STT: Faster-Whisper Small (CPU INT8)
- LLM: Ollama Qwen2.5 7B (GPU 가속)
- 오디오: Windows WASAPI Loopback (soundcard)
"""

import io
import os
import sys
import ctypes.util
from datetime import datetime, timedelta
from pathlib import Path
import queue
import signal
import threading
import time

# Windows 콘솔 UTF-8 인코딩 및 필수 시스템 라이브러리(ole32.dll 등) 경로 강제 복구
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    class Fore:
        CYAN = GREEN = YELLOW = RED = MAGENTA = BLUE = WHITE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

import config
from core.audio_capture import AudioCaptureThread
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine


class LectureAssistant:
    def __init__(self):
        # 실행 세션 타임스탬프 기반 저장 폴더 생성
        self.session_time = datetime.now()
        self.session_dir = config.BASE_OUTPUT_DIR / f"lecture_{self.session_time.strftime('%Y%m%d_%H%M%S')}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.transcript_path = self.session_dir / "transcript.txt"
        self.summary_path = self.session_dir / "summary.md"
        self.report_path = self.session_dir / "final_lecture_report.md"

        # 스레드 및 큐
        self.audio_queue = queue.Queue(maxsize=30)
        self.stop_event = threading.Event()
        self.capture_thread = None

        # 엔진 초기화
        self.stt_engine = STTEngine(
            model_name=config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            language=config.WHISPER_LANGUAGE,
            beam_size=config.WHISPER_BEAM_SIZE,
            vad_filter=config.WHISPER_VAD_FILTER,
        )

        self.llm_engine = LLMEngine(
            base_url=config.OLLAMA_BASE_URL,
            model=config.OLLAMA_MODEL,
            timeout=config.OLLAMA_TIMEOUT,
        )

        # 강의 데이터 버퍼
        self.full_transcripts = []   # [(timestamp_str, text)]
        self.pending_summary_texts = []
        self.accumulated_audio_sec = 0.0
        self.start_time = None
        self.summary_count = 0

    def print_banner(self):
        print(f"{Fore.CYAN}{Style.BRIGHT}======================================================================")
        print("   [LectureAI] Zoom 실시간 강의 자막 & AI 스마트 요약 비서")
        print("======================================================================" + f"{Style.RESET_ALL}")
        print(f" * 음성인식 엔진 : Whisper {config.WHISPER_MODEL.upper()} (CPU INT8 고속 전사)")
        print(f" * 요약 인공지능 : Ollama {self.llm_engine.active_model} (로컬 온디바이스)")
        print(f" * 결과 저장경로 : {self.session_dir.resolve()}")
        print(f"{Fore.CYAN}======================================================================{Style.RESET_ALL}\n")

    def _format_elapsed(self) -> str:
        if self.start_time is None:
            return "00:00:00"
        elapsed = datetime.now() - self.start_time
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def write_transcript_entry(self, time_tag: str, text: str):
        """전사된 자막을 파일에 즉시 추가합니다."""
        line = f"[{time_tag}] {text}\n"
        with self.transcript_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def write_summary_entry(self, markdown_text: str):
        """구간 요약 마크다운을 파일에 기록합니다."""
        with self.summary_path.open("a", encoding="utf-8") as f:
            f.write(f"\n\n{markdown_text}\n\n---\n")

    def _summary_worker(self, chunk_text: str, status_label: str):
        """백그라운드 스레드에서 비동기로 요약을 수행하여 실시간 자막 출력을 방해하지 않습니다."""
        try:
            summary_result = self.llm_engine.summarize_chunk(chunk_text, status_label)
            print(f"\n{Fore.GREEN}{Style.BRIGHT}{'=' * 50}\n[AI 강의 요약 - {status_label}]\n{'=' * 50}{Style.RESET_ALL}", flush=True)
            print(f"{Fore.WHITE}{summary_result}\n", flush=True)
            self.write_summary_entry(summary_result)
        except Exception as e:
            print(f"\n{Fore.RED}[요약 오류 발생] {e}{Style.RESET_ALL}", flush=True)
            # 요약에 실패하더라도 원문 내용이 유실되지 않도록 파일에 보존 기록
            fallback_note = f"### [{status_label}] 구간 기록\n> *(AI 응답 지연으로 요약 생략 - 원문 보존)*\n\n{chunk_text}"
            self.write_summary_entry(fallback_note)

    def trigger_periodic_summary(self, is_final: bool = False):
        """누적된 전사 텍스트를 바탕으로 3분 단위 요약을 실행합니다."""
        if not self.pending_summary_texts:
            return

        chunk_text = "\n".join(self.pending_summary_texts).strip()
        if len(chunk_text) < 15:
            # 텍스트가 너무 짧으면 다음 주기로 누적 유지
            return

        # 새 자막이 다음 구간으로 누적되도록 즉시 버퍼 복사 후 비움
        self.pending_summary_texts.clear()
        self.summary_count += 1
        elapsed_str = self._format_elapsed()
        status_label = f"종료 직전 마지막 구간 ({elapsed_str})" if is_final else f"{self.summary_count}회차 구간 ({elapsed_str})"

        print(f"\n{Fore.MAGENTA}{Style.BRIGHT}[AI 요약 분석 시작... ({status_label}) - 백그라운드 실행]{Style.RESET_ALL}", flush=True)

        if is_final:
            # 프로그램 종료 시점에는 요약 완료 후 파일 저장이 필요하므로 동기 실행
            self._summary_worker(chunk_text, status_label)
        else:
            # 강의 중에는 별도 스레드로 분리하여 실시간 자막 출력이 1초도 끊기지 않음
            t = threading.Thread(
                target=self._summary_worker,
                args=(chunk_text, status_label),
                daemon=True,
            )
            t.start()

    def generate_final_lecture_report(self):
        """전체 강의 종료 시 통합 종합 강의 노트를 생성합니다."""
        if not self.full_transcripts:
            print("[안내] 수집된 강의 내용이 없어 최종 리포트를 생성하지 않습니다.")
            return

        total_text = "\n".join(f"[{t[0]}] {t[1]}" for t in self.full_transcripts)
        if len(total_text) < 50:
            print("[안내] 강의 전사 분량이 너무 적어 최종 리포트 작성을 건너뜁니다.")
            return

        print(f"\n{Fore.CYAN}{Style.BRIGHT}==================================================")
        print("[리포트] 전체 강의 종합 분석 리포트를 생성하고 있습니다...")
        print("==================================================" + f"{Style.RESET_ALL}")

        try:
            report_md = self.llm_engine.generate_final_report(total_text)
            header = f"# 강의 종합 리포트\n- 일시: {self.session_time.strftime('%Y-%m-%d %H:%M:%S')}\n- 총 강의 시간: {self._format_elapsed()}\n\n---\n\n"
            with self.report_path.open("w", encoding="utf-8") as f:
                f.write(header + report_md)

            print(f"\n{Fore.GREEN}{Style.BRIGHT}[완료] 최종 종합 리포트가 성공적으로 저장되었습니다!{Style.RESET_ALL}")
            print(f"[저장 경로] 리포트 파일: {self.report_path.resolve()}\n")
        except Exception as e:
            print(f"{Fore.RED}[최종 리포트 생성 오류] {e}{Style.RESET_ALL}")

    def run(self):
        print(f"\n{Fore.CYAN}[1/3] 로컬 AI 엔진(Ollama) 상태 확인 중...{Style.RESET_ALL}")
        llm_ready = self.llm_engine.check_connection()
        if llm_ready:
            print(f"      -> {Fore.GREEN}[V] Ollama 정상 연결 (활성 모델: {self.llm_engine.active_model}){Style.RESET_ALL}")
        else:
            print(f"      -> {Fore.YELLOW}[!] Ollama 미연결 (실시간 자막 전용 모드로 작동){Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}[2/3] 한국어 음성인식 모델 적재 중...{Style.RESET_ALL}")
        self.stt_engine.load_model()
        print(f"      -> {Fore.GREEN}[V] Whisper 모델 준비 완료{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}[3/3] Windows 오디오(WASAPI) 스트림 연결 중...{Style.RESET_ALL}")
        self.capture_thread = AudioCaptureThread(
            audio_queue=self.audio_queue,
            stop_event=self.stop_event,
            target_rate=config.TARGET_SAMPLE_RATE,
            chunk_sec=config.CHUNK_DURATION_SEC,
        )
        self.capture_thread.start()
        print(f"      -> {Fore.GREEN}[V] 스피커 출력 연결 완료: {self.capture_thread.device_name}{Style.RESET_ALL}\n")

        # 메인 대시보드 배너 출력
        self.print_banner()

        self.start_time = datetime.now()
        # 요약 파일 헤더 작성
        with self.summary_path.open("w", encoding="utf-8") as f:
            f.write(f"# [실시간 강의 요약 노트]\n- 강의 일시: {self.session_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        print(f"{Fore.GREEN}{Style.BRIGHT}──────────────────────────────────────────────────────────────────────")
        print(" ▶ 실시간 강의 분석이 시작되었습니다. (강의 소리가 감지되면 자막이 표시됩니다)")
        print("   수업이 종료되면 언제든 [Ctrl + C]를 눌러 종합 리포트를 저장하세요.")
        print(f"──────────────────────────────────────────────────────────────────────{Style.RESET_ALL}\n")

        try:
            while not self.stop_event.is_set():
                try:
                    # 1초 타임아웃으로 오디오 청크 가져오기
                    audio_chunk = self.audio_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                self.accumulated_audio_sec += config.CHUNK_DURATION_SEC
                time_tag = self._format_elapsed()

                # STT 전사 수행
                text = self.stt_engine.transcribe(audio_chunk)
                if text:
                    print(f"{Fore.CYAN}[{time_tag}]{Style.RESET_ALL} {text}", flush=True)
                    self.write_transcript_entry(time_tag, text)
                    self.full_transcripts.append((time_tag, text))
                    self.pending_summary_texts.append(f"[{time_tag}] {text}")

                # 3분(180초) 도달 시 구간 요약 트리거
                if self.accumulated_audio_sec >= config.SUMMARY_INTERVAL_SEC:
                    self.trigger_periodic_summary(is_final=False)
                    self.accumulated_audio_sec = 0.0

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[종료 신호 감지] 강의 녹음을 중단하고 후속 처리를 진행합니다...{Style.RESET_ALL}")
        finally:
            self.shutdown()

    def shutdown(self):
        """정상 및 비정상 종료 시 미처리 큐 비우기 및 최종 리포트 저장"""
        self.stop_event.set()
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)

        # 1. 큐에 남아있는 미처리 오디오 모두 전사
        remaining_count = self.audio_queue.qsize()
        if remaining_count > 0:
            print(f"[정리 중] 큐에 남아있는 {remaining_count}개의 오디오 블록을 전사합니다...")
            while not self.audio_queue.empty():
                try:
                    chunk = self.audio_queue.get_nowait()
                    time_tag = self._format_elapsed()
                    text = self.stt_engine.transcribe(chunk)
                    if text:
                        print(f"{Fore.CYAN}[{time_tag} 잔여]{Style.RESET_ALL} {text}")
                        self.write_transcript_entry(time_tag, text)
                        self.full_transcripts.append((time_tag, text))
                        self.pending_summary_texts.append(f"[{time_tag}] {text}")
                except queue.Empty:
                    break

        # 2. 마지막 미요약 구간 요약
        if self.pending_summary_texts:
            print("[정리 중] 마지막 미요약 구간에 대해 AI 요약을 수행합니다...")
            self.trigger_periodic_summary(is_final=True)

        # 3. 전체 강의 종합 리포트 생성
        self.generate_final_lecture_report()

        print(f"{Fore.GREEN}{Style.BRIGHT}" + "=" * 70)
        print("[완료] 모든 강의 기록 및 요약 작업이 안전하게 완료되었습니다.")
        print(f"* 전체 자막 파일  : {self.transcript_path.resolve()}")
        print(f"* 3분 구간 요약   : {self.summary_path.resolve()}")
        if self.report_path.exists():
            print(f"* 종합 분석 리포트: {self.report_path.resolve()}")
        print("=" * 70 + f"{Style.RESET_ALL}")


def main():
    assistant = LectureAssistant()
    assistant.run()


if __name__ == "__main__":
    main()
