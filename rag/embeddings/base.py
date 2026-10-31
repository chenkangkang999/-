"""向量化协议：BGE-M3（含 LoRA 微调版）都实现同一接口。"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math_sqrt(sum(x * x for x in a)) * math_sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def math_sqrt(value: float) -> float:
    return value ** 0.5
