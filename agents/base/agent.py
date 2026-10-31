"""Agent 基类：统一「输入校验 → 执行 → 埋点 → 失败降级」的骨架。"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agents.base.context import AgentContext
from agents.base.message import AgentMessage

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    agent: str
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "content": self.content,
            "citations": self.citations,
            "metadata": self.metadata,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class BaseAgent(ABC):
    name: str = "base"
    description: str = ""
    system_prompt: str = ""

    @abstractmethod
    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        """子类唯一需要实现的方法。"""

    def run(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        started = time.perf_counter()
        try:
            result = self._execute(context, message)
        except Exception as exc:  # noqa: BLE001 - 单个 Agent 失败不能拖垮整条链路
            logger.exception("agent %s failed", self.name)
            result = AgentResult(
                agent=self.name, content="", metadata={}, error=f"{type(exc).__name__}: {exc}"
            )
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        context.record(self.name, result.to_dict())
        return result
