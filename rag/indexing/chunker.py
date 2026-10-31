"""简易切片：按段落聚合到目标长度，保留 overlap，便于后续替换为语义切片。"""
from __future__ import annotations


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    return [text[start:start + size] for start in range(0, len(text), step)]
