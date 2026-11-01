from __future__ import annotations

import os

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register
from agents.debate.graph import build_debate_graph
from agents.llm.support import emit_started, evidence, failure_result, upstream_payload


@register
class DebateAgent(BaseAgent):
    name = "debate"
    description = "基于真实上游意见的 LangGraph 分歧识别、交叉质证与有界仲裁"
    system_prompt = "agents/prompts/debate_detect.md"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        emit_started(context, self.name)
        try:
            return self._debate(context, message)
        except Exception as exc:  # noqa: BLE001 - model output must not enter exception logs
            return failure_result(self.name, exc)

    def _debate(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        payload = upstream_payload(context, message, exclude=("debate", "explainer", "safety"))
        # An explicit empty list means this module supplied observations, not a
        # diagnostic position. Keep older colleagues' content-only contracts.
        sources = [step for step in payload["upstream"]
                   if step["available"] and step["agent"] != "retrieval"
                   and step.get("content", "").strip()
                   and ("diagnostic_opinions" not in step["metadata"]
                        or bool(step["metadata"]["diagnostic_opinions"]))]
        if len(sources) < 2:
            return AgentResult(agent=self.name, content="", metadata={
                "status": "skipped", "reason": "insufficient_upstream_data", "rounds": [],
            })
        payload["upstream"] = sources
        max_rounds = int(os.getenv("DEBATE_MAX_ROUNDS", "2"))
        if not 1 <= max_rounds <= 5:
            raise ValueError("INVALID_DEBATE_MAX_ROUNDS")
        state = build_debate_graph().invoke({
            "context": context, "payload": payload, "round": 0,
            "max_rounds": max_rounds, "rounds": [], "llm_calls": [],
        })
        verdict = state.get("verdict")
        ids = set(verdict["citation_ids"]) if verdict else set()
        return AgentResult(
            agent=self.name,
            content=verdict["conclusion"] if verdict else state["detection"]["summary"],
            citations=[item for item in evidence(context) if item["chunk_id"] in ids],
            metadata={"status": "completed", "engine": "langgraph",
                      "disagreements": state["detection"]["conflicts"],
                      "rounds": state.get("rounds", []), "verdict": verdict,
                      "llm_calls": state["llm_calls"]},
        )
