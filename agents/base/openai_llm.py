"""OpenAI 兼容客户端（DeepSeek/Qwen 等只要改 LLM_BASE_URL 即可）。"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass
class OpenAILLM:
    model: str = ""
    base_url: str = ""
    timeout: float = 60.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        self.model = self.model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.base_url = (self.base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"}
        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001 - 统一重试后抛出
                last_error = exc
        raise RuntimeError(f"LLM 调用失败: {last_error}")
