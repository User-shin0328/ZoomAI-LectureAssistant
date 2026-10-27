"""
LLM 요약 엔진 모듈 (core/llm_engine.py)
Ollama 로컬 REST API를 통해 실시간 강의 자막을 분석하고
구간 요약 및 최종 종합 강의 노트를 생성합니다.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from typing import List, Optional
import requests


def find_free_port(start_port: int = 11434, max_tries: int = 20) -> int:
    """start_port부터 시작하여 실제 사용 가능한 비어있는 로컬 TCP 포트를 찾습니다."""
    for p in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start_port


class LLMEngine:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        fallback_models: Optional[List[str]] = None,
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_models = fallback_models or []
        self.timeout = timeout
        self.active_model = model

    def _is_active_ollama(self, url: str) -> bool:
        """해당 URL이 실제 정상 응답하는 Ollama 서버인지 점검합니다."""
        try:
            res = requests.get(f"{url}/api/tags", timeout=2)
            return res.status_code == 200 and "models" in res.json()
        except Exception:
            return False

    def _verify_models(self) -> bool:
        """Ollama 서버에서 사용 가능한 모델을 점검하고 활성 모델을 결정합니다."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if res.status_code == 200:
                available_models = [m["name"] for m in res.json().get("models", [])]

                # 1. 지정된 메인 모델 검색
                matching = [m for m in available_models if self.model in m]
                if matching:
                    self.active_model = matching[0]
                    return True

                # 2. 설치된 모델이 있으면 첫 번째 설치 모델 사용
                if available_models:
                    self.active_model = available_models[0]
                    return True
                return False
        except Exception:
            return False

    def check_connection(self) -> bool:
        """
        포트 충돌 방지 및 다이내믹 포트 자동 할당:
        1. 기본 포트(11434)에 Ollama가 이미 돌고 있다면 즉시 연결
        2. 만약 11434가 다른 프로그램에 의해 점유되어 있거나 비정상이면,
           11435, 11436 등 비어있는 포트를 찾아 Ollama를 해당 포트로 자동 가동
        """
        # 1. 기본 설정 URL 점검
        if self._is_active_ollama(self.base_url):
            return self._verify_models()

        # 2. 다른 포트(11434~11442)에 이미 가동 중인 Ollama가 있는지 자동 스캔
        for p in range(11434, 11443):
            candidate = f"http://127.0.0.1:{p}"
            if self._is_active_ollama(candidate):
                self.base_url = candidate
                return self._verify_models()

        # 3. 가동 중인 Ollama가 없거나 포트 11434가 타 프로그램에 점유된 경우 -> 비어있는 포트 탐색 후 가동
        free_port = find_free_port(11434, max_tries=20)

        ollama_bin = None
        local_app = os.environ.get("LOCALAPPDATA", "")
        candidate_bin = os.path.join(local_app, "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(candidate_bin):
            ollama_bin = candidate_bin
        else:
            ollama_bin = shutil.which("ollama")

        if ollama_bin and os.path.isfile(ollama_bin):
            env = os.environ.copy()
            env["OLLAMA_HOST"] = f"127.0.0.1:{free_port}"
            try:
                flags = 0
                if sys.platform.startswith("win"):
                    flags = subprocess.CREATE_NO_WINDOW
                # Ollama 엔진의 내부 디버그/GIN 로그를 숨기기 위해 DEVNULL로 리다이렉트
                subprocess.Popen(
                    [ollama_bin, "serve"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
                # 최대 5초간 서버 응답 대기
                for _ in range(10):
                    time.sleep(0.5)
                    candidate = f"http://127.0.0.1:{free_port}"
                    if self._is_active_ollama(candidate):
                        self.base_url = candidate
                        return self._verify_models()
            except Exception:
                pass

        return False

    def _call_ollama(self, prompt: str, system_prompt: str, max_tokens: int = 450) -> str:
        """Ollama /api/generate 엔드포인트를 호출합니다."""
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.active_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 2048,           # CPU 컨텍스트 로딩 속도 최적화
                "num_predict": max_tokens, # 토큰 생성 상한 제한 (연산 시간 절반 단축)
            },
        }

        try:
            response = requests.post(endpoint, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Ollama 호출 시간 초과 (타임아웃 {self.timeout}초 경과)")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama 호출 실패 ({self.active_model}): {e}")

    def summarize_chunk(self, transcript_chunk: str, chunk_time_label: str) -> str:
        """
        3분 단위의 강의 텍스트 구간을 분석하여 마크다운 포맷으로 핵심 요약합니다.
        """
        system_prompt = (
            "당신은 대학 및 IT 전문 강의를 실시간으로 기록하고 정리하는 최고의 AI 강의 조교입니다. "
            "강의자의 발언에서 군더더기(말버릇, 추임새 등)를 제거하고 사실에 입각하여 구조적으로 정리하세요. "
            "반드시 한국어로 정중하고 명확한 마크다운 형식으로 작성하세요."
        )

        user_prompt = f"""다음은 최근 강의 약 3분간 진행된 음성 전사 내용입니다:

---
{transcript_chunk}
---

위 내용을 바탕으로 아래 형식에 맞춰 요약해 주세요:

### 📌 [{chunk_time_label}] 핵심 주제
(이 구간에서 강사가 설명한 핵심 개념 1~2문장)

#### 📝 주요 내용 정리
- (핵심 요점 1)
- (핵심 요점 2)
- (핵심 요점 3)

#### 💡 중요 키워드 & 용어
- **키워드**: 간단한 정의 및 맥락 설명
"""
        return self._call_ollama(user_prompt, system_prompt, max_tokens=450)

    def generate_final_report(self, full_transcript: str) -> str:
        """
        강의 종료 시 전체 전사 내용을 종합 분석하여
        강의 내용과 핵심 요약 중심으로 최종 리포트를 생성합니다.
        """
        system_prompt = (
            "당신은 강의 내용을 빠짐없이 명확하게 정리하는 전문 AI 강의 노트 작성 비서입니다. "
            "강의자의 발언 맥락을 살려 핵심 내용을 논리적이고 깔끔하게 정리하세요. "
            "불필요한 서론이나 사족 없이 요청된 두 가지 항목(핵심 요약, 강의 세부 내용)만 마크다운으로 작성하세요."
        )

        user_prompt = f"""다음은 오늘 진행된 강의의 전체 음성 전사본입니다:

---
{full_transcript}
---

위 내용을 바탕으로 부가적인 미사여구 없이 아래 두 가지 구성으로만 정리해 주세요:

# 📌 강의 종합 리포트

## 1. 핵심 요약
(전체 강의를 관통하는 핵심 메시지와 요점을 3~5개의 불릿 포인트로 일목요연하게 정리)

## 2. 강의 세부 내용 정리
(강의 흐름에 따라 진행된 주요 개념, 설명, 예시를 소주제별로 빠짐없이 구조화하여 상세히 정리)
"""
        return self._call_ollama(user_prompt, system_prompt, max_tokens=1500)
