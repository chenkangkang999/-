"""检索服务：当前是数据库关键词兜底实现，P2 接 Milvus 混合检索后替换本文件。

对外只暴露 `search_chunks(query, top_k)`，Agent 侧不关心底层是 Milvus 还是 SQL。
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from apps.rag.models import Chunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source: str
    title: str
    snippet: str
    score: float

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
        }


def search_chunks(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    query = (query or "").strip()
    if not query:
        return []
    keywords = [token for token in query.replace("，", " ").replace(",", " ").split() if token]
    condition = Q()
    for keyword in keywords[:5]:
        condition |= Q(text__icontains=keyword)
    rows = (
        Chunk.objects.select_related("document")
        .filter(condition)
        .order_by("-document__published_at")[:top_k]
    )
    return [
        RetrievedChunk(
            chunk_id=str(row.pk),
            source=row.document.source or row.document.get_authority_display(),
            title=row.document.title,
            snippet=row.text[:300],
            score=1.0,
        )
        for row in rows
    ]
