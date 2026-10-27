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
        강의 텍스트 구간을 분석하여 뻔한 개념 정의는 배제하고,
        강사가 실제로 강조한 실무 알맹이와 인사이트 중심으로 마크다운 요약합니다.
        """
        system_prompt = (
            "당신은 IT 전문 강의의 핵심 알맹이만 정확히 짚어내는 수석 보안 분석가이자 전문 강의 노트 정리 비서입니다.\n"
            "[작성 원칙]\n"
            "1. '로그란 무엇인가', 'AI란 무엇인가' 같은 뻔한 교과서적/사전적 단어 뜻 풀이는 절대로 작성하지 마세요.\n"
            "2. '~에 대해 설명했습니다', '~를 다루었습니다' 같은 3자 관찰자 문체를 쓰지 말고, 수강생이 바로 읽고 복습할 수 있는 완성형 문장이나 명사형 불릿으로 작성하세요.\n"
            "3. 강사가 실제로 발언한 실무 팁, 현업의 딜레마, 법령/제도 변화 일정, 구체적 사례, 실습 안내 등 '실제 알맹이'에만 집중하세요.\n"
            "4. 반드시 한국어로 정중하고 가독성 높은 마크다운 형식으로 작성하세요."
        )

        user_prompt = f"""다음은 최근 강의에서 음성 인식된 전사 텍스트입니다:
---
{transcript_chunk}
---

위 텍스트에서 뻔한 교과서적 단어 정의는 모두 빼고, 강사가 실제로 전달한 알맹이만 아래 형식으로 정리하세요:

### 📌 [{chunk_time_label}] 핵심 테마
(이 구간에서 강사가 전달하고자 하는 핵심 메시지 1문장)

#### 🎯 강사 강조 포인트 & 실무 인사이트
- (강사가 강조한 실무 팁, 현업의 딜레마, 주의점, 구체적 사례 등)
- (수치, 법/제도 일정, 실무 충돌 등 실질적 내용)

#### 📋 세부 강의 내용 정리
- (실제 강의 흐름에 따른 주요 설명 내용 2~3줄 요약)
"""
        return self._call_ollama(user_prompt, system_prompt, max_tokens=450)

    def generate_final_report(self, full_transcript: str) -> str:
        """
        강의 종료 시 전체 전사 내용을 종합 분석하여
        사전식 단어 정의 없이 실무 인사이트와 세부 강의 흐름 중심의 최종 마크다운 리포트를 생성합니다.
        """
        system_prompt = (
            "당신은 전체 강의 전사본을 바탕으로 시험 및 실무 복습용 최고급 강의 노트를 작성하는 전문 AI 비서입니다.\n"
            "[작성 원칙]\n"
            "1. 뻔한 교과서적 개념 정의는 일절 배제하고, 전체 강의를 관통하는 핵심 흐름과 강사의 실무 발언 알맹이만 구조화하세요.\n"
            "2. 강사가 실제로 언급한 제도 변화, 실무 현장의 차이점, 실습 안내를 명확하게 포함하세요.\n"
            "3. 군더더기 서론 없이 깔끔한 마크다운 리포트로 작성하세요."
        )

        user_prompt = f"""다음은 오늘 진행된 전체 강의의 음성 전사본입니다:
---
{full_transcript}
---

위 내용을 바탕으로 교과서적 개념 설명은 배제하고, 강사의 발언을 종합하여 아래 마크다운 양식으로 정리해 주세요:

# 🎓 강의 종합 마크다운 노트

## 1. 📌 강의 한 줄 요약 & 핵심 테마
(전체 강의의 핵심 목적과 주요 방향 2~3문장)

## 2. 🎯 강사가 강조한 핵심 실무 인사이트 (Top 5)
- (1. 제도/일정 변화, 실무 현장의 딜레마, 관제/엔지니어링 핵심 등)
- (2. ...)
- (3. ...)
- (4. ...)
- (5. ...)

## 3. 📋 세부 주제별 강의 내용 정리
(오전/오후 또는 주제 흐름별로 소제목을 나누고, 강사가 언급한 실제 사례와 설명을 불릿 포인트로 상세 정리)

## 4. 🛠️ 실습 및 액션 아이템
(강사가 지시한 실습 내용, 점검 도구, 수동/자동 진단 비교 등)
"""
        return self._call_ollama(user_prompt, system_prompt, max_tokens=1500)
