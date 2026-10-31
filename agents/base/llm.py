"""LLM 客户端抽象：`complete()` 是唯一替换点。

没有配置 API Key 时自动降级为 `EchoLLM`，保证骨架/CI 可离线跑通；
接真实模型只需实现 `LLMClient` 并注册到 `get_llm_client()`。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class LLMClient(Protocol):
    model: str

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass
class EchoLLM:
    """离线占位实现：把输入回显成结构化占位答案，便于联调与单测。"""

    model: str = "echo"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return f"[offline-llm] {user_prompt.strip()[:200]}"


def get_llm_client() -> LLMClient:
    if not os.getenv("LLM_API_KEY"):
        return EchoLLM()
    from agents.base.openai_llm import OpenAILLM  # 延迟 import：没装 openai 也能跑

    return OpenAILLM()
