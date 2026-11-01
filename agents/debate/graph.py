"""Lazy LangGraph entry point; web startup does not require the AI extras."""
from __future__ import annotations

from typing import Protocol


class DebateGraph(Protocol):
    def invoke(self, state: dict) -> dict: ...


def build_debate_graph() -> DebateGraph:
    try:
        from agents.debate.langgraph_impl import build_graph
    except ImportError as exc:  # pragma: no cover - explicit missing dependency
        raise RuntimeError("DEBATE_DEPENDENCY_UNAVAILABLE: langgraph") from exc
    return build_graph()
