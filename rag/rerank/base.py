"""重排协议：Cross-encoder 或 LLM 重排都实现 `rerank()`。"""
from __future__ import annotations

from typing import Protocol

from rag.retrieval.base import Hit


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[Hit], top_k: int = 5) -> list[Hit]: ...
