"""Agent 之间传递的消息与证据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Citation:
    """一条可溯源的证据（答案里每个结论都应能点回这里）。"""

    chunk_id: str
    source: str
    title: str
    snippet: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
        }


@dataclass
class AgentMessage:
    """进入/离开 Agent 的统一消息体。"""

    content: str
    role: str = "user"
    citations: list[Citation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
