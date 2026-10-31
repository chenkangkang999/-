"""检索评估指标：纯 Python 实现，便于单测与离线批量评测。"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    hits = sum(1 for doc_id in ranked[:k] if doc_id in relevant_set)
    return hits / len(relevant_set)


def mrr(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    relevant_set = set(relevant)
    for index, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant_set:
            return 1.0 / index
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    dcg = sum(
        1.0 / math.log2(index + 1)
        for index, doc_id in enumerate(ranked[:k], start=1)
        if doc_id in relevant_set
    )
    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0
