"""检索器协议：Milvus / BM25 / 混合检索都实现同一个接口。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    text: str
    score: float
    source: str = ""


class Retriever(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[Hit]: ...


class HybridRetriever:
    """稠密 + 稀疏融合占位：P2 接入 Milvus 与 BM25 后填充实现。"""

    def __init__(self, dense: Retriever | None = None, sparse: Retriever | None = None,
                 alpha: float = 0.5) -> None:
        self.dense = dense
        self.sparse = sparse
        self.alpha = alpha

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        merged: dict[str, Hit] = {}
        for retriever, weight in ((self.dense, self.alpha), (self.sparse, 1 - self.alpha)):
            if retriever is None:
                continue
            for hit in retriever.search(query, top_k=top_k):
                fused = hit.score * weight
                current = merged.get(hit.chunk_id)
                if current is None or fused > current.score:
                    merged[hit.chunk_id] = Hit(hit.chunk_id, hit.text, fused, hit.source)
        return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:top_k]
