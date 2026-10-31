"""辩论编排（P3 用 LangGraph 实现）。

当前只定义契约，真实图在接入 langgraph 后替换：
  build_debate_graph() -> CompiledGraph，输入 AgentResult 列表，输出收敛结论。
"""
from __future__ import annotations

from typing import Protocol


class DebateGraph(Protocol):
    def invoke(self, state: dict) -> dict: ...


def build_debate_graph() -> DebateGraph:
    try:
        from agents.debate.langgraph_impl import build_graph
    except ImportError as exc:  # pragma: no cover - 未装 langgraph 时走降级
        raise RuntimeError("未安装 langgraph，请先 pip install -r requirements/ai.txt") from exc
    return build_graph()
