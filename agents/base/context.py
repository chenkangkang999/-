"""一次协作运行的共享上下文（患者事实 + 预算 + 追踪 id）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    consultation_id: int | None = None
    user_id: int | None = None
    trace_id: str = ""
    patient: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)

    def record(self, agent: str, payload: dict[str, Any]) -> None:
        self.steps.append({"agent": agent, **payload})
