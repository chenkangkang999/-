from __future__ import annotations

import json

import pytest

from agents.base.context import AgentContext
from agents.base.coordinator import Coordinator
from agents.contracts import LLMResponse, LLMUsage

pytestmark = pytest.mark.unit


class PipelineTestProvider:
    """Only an explicitly injected test provider; never enabled by the app."""

    def complete(self, system_prompt, user_prompt, *, agent):
        del system_prompt, user_prompt
        if agent == "triage":
            payload = {"chief_complaint": "最近有点咳嗽", "symptoms": [{"name": "咳嗽", "source_text": "咳嗽", "status": "present"}], "differentials": []}
        elif agent == "debate":
            payload = {"conflicts": [], "summary": "测试输入没有提供真实分歧。"}
        elif agent == "explainer":
            payload = {
                "soap": {"subjective": "测试主诉", "objective": "未提供检查结果",
                         "assessment": "测试信息不足", "plan": "请咨询医师"},
                "explanation": "这是测试解释，不替代医师。",
                "care_guidance": ["必要时就医"], "citation_ids": [],
            }
        elif agent == "safety":
            payload = {"decision": "pass", "reasons": [], "severity": "low",
                       "regulation_ids": [], "approved_text": ""}
        else:
            raise AssertionError(f"unexpected test LLM caller: {agent}")
        return LLMResponse(json.dumps(payload, ensure_ascii=False), LLMUsage(10, 10, 20),
                           "explicit-pipeline-test")


def make_context():
    return AgentContext(facts={"_llm": PipelineTestProvider()})


def test_pipeline_runs_all_agents_and_flags_red_flag():
    result = Coordinator().run("胸痛，呼吸困难，持续十分钟", make_context())
    names = [step["agent"] for step in result.steps]
    assert names == ["triage", "risk", "safety"]
    assert result.risk_level == "critical"
    assert "急诊" in result.reply or "立即" in result.reply


def test_reply_contains_disclaimer_when_safety_runs():
    result = Coordinator().run("最近有点咳嗽", make_context())
    assert "不构成" in result.reply or "不替代" in result.reply or "急诊" in result.reply
