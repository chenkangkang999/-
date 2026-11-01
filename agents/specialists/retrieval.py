from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register


@register
class RetrievalAgent(BaseAgent):
    name = "retrieval"
    description = "全语料BM25/真实BGE+Milvus混合检索、可选重排、引用溯源"
    system_prompt = "你是检索专家，只提供有出处的证据，不做诊断结论。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        from django.contrib.auth import get_user_model

        from apps.rag.services.search import search_with_status

        emit = context.facts.get("_emit")
        if callable(emit):
            emit(self.name, "started")
        user = get_user_model().objects.filter(pk=context.user_id).first() if context.user_id else None
        symptoms = context.facts.get("standardized_symptoms", [])
        query = " ".join(symptoms) if symptoms else context.facts.get("chief_complaint") or message.content
        outcome = search_with_status(query, user=user, trace_id=context.trace_id)
        citations = [chunk.to_dict() for chunk in outcome.results]
        if outcome.status == "not_connected":
            text = "知识检索尚未接入或索引/模型版本未就绪，本次无检索证据。"
        elif outcome.status == "error":
            text = "知识检索调用失败，本次不提供未经核验的引用。"
        else:
            text = f"检索到 {len(citations)} 条可追溯证据。" if citations else "已检索配置的语料，但没有命中证据。"
        if outcome.degraded:
            text += " 当前使用CPU BM25降级检索，未启用BGE/Milvus。"
        if any(item["corpus_kind"] == "community_qa" for item in citations):
            text += " 社区问答不是临床指南，不能作为个体用药推荐依据。"
        return AgentResult(agent=self.name, content=text, citations=citations, metadata=outcome.metadata(), error=outcome.error_code if outcome.status == "error" else None)
