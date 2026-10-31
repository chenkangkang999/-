from __future__ import annotations

import logging

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register

logger = logging.getLogger(__name__)


@register
class RetrievalAgent(BaseAgent):
    name = "retrieval"
    description = "RAG 混合检索、重排、引用溯源"
    system_prompt = "你是检索专家，只提供有出处的证据，不做诊断结论。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        try:
            from apps.rag.services.search import search_chunks

            chunks = search_chunks(message.content, top_k=5)
        except Exception as exc:  # noqa: BLE001 - 检索不可用时降级，不阻断问诊
            logger.warning("retrieval unavailable: %s", exc)
            return AgentResult(
                agent=self.name,
                content="检索暂不可用，本次回答不含外部证据。",
                citations=[],
                metadata={"hits": 0, "degraded": True},
            )
        citations = [chunk.to_dict() for chunk in chunks]
        summary = f"检索到 {len(citations)} 条证据。" if citations else "未检索到可靠证据。"
        return AgentResult(agent=self.name, content=summary, citations=citations,
                           metadata={"hits": len(citations)})
