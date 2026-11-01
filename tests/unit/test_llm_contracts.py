"""Explicit scripted providers and HTTP transports; never call a medical model in CI."""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.contracts import LLMResponse, LLMUsage
from agents.llm import LLMConfigurationError, LLMProviderError, OpenAICompatibleClient
from agents.llm.support import upstream_payload
from agents.specialists.debate_agent import DebateAgent
from agents.specialists.explainer import ExplainerAgent
from agents.specialists.safety import SafetyAgent

pytestmark = pytest.mark.unit


class ScriptedProvider:
    model = "unit-test-provider"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system_prompt, user_prompt, *, agent):
        self.calls.append({"system": system_prompt, "payload": json.loads(user_prompt),
                           "agent": agent})
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        return LLMResponse(content, LLMUsage(20, 10, 30), self.model, "unit-request")


def context_with(provider, *, candidate=None):
    context = AgentContext(facts={"_llm": provider})
    if candidate is not None:
        context.facts["candidate_text"] = candidate
    context.steps = [
        {"agent": "triage", "content": "症状信息尚不完整", "metadata": {}, "citations": []},
        {"agent": "risk", "content": "尚不能排除风险", "metadata": {"risk_level": "low"}},
        {"agent": "medication", "content": "可以排除风险", "metadata": {}},
        {"agent": "retrieval", "content": "检索结果", "metadata": {}, "citations": [{
            "chunk_id": "chunk-unit", "title": "测试证据", "source": "unit://source",
            "snippet": "仅用于测试证据传递", "score": 0.9,
        }]},
    ]
    return context


def explanation():
    return {"soap": {"subjective": "用户报告咳嗽", "objective": "未提供体温或检查结果",
                     "assessment": "信息不足，不能确诊", "plan": "补充持续时间并咨询医师"},
            "explanation": "以上仅为信息整理，不替代医师。", "care_guidance": ["补充病史"],
            "citation_ids": ["chunk-unit"]}


def review(decision="pass", **kwargs):
    return {"decision": decision, "reasons": [], "severity": "low", "regulation_ids": [],
            "approved_text": "", **kwargs}


def test_explainer_reads_upstream_and_preserves_sources():
    provider = ScriptedProvider(explanation())
    context = context_with(provider)
    context.facts["history"] = [{"role": "user", "content": "前一轮信息"}]
    result = ExplainerAgent().run(context, AgentMessage("咳嗽"))
    assert result.error is None
    assert result.metadata["soap"]["objective"] == "未提供体温或检查结果"
    assert result.citations[0]["chunk_id"] == "chunk-unit"
    assert provider.calls[0]["payload"]["history"][0]["content"] == "前一轮信息"
    assert result.metadata["llm"]["usage"]["input_tokens"] == 20
    assert result.metadata["requires_safety_review"] is True


def test_prompt_snapshot_never_serializes_private_dependencies():
    context = context_with(ScriptedProvider())
    context.facts["_api_key"] = "top-secret"
    context.patient = {"allergies": [], "_private": "never-export"}
    payload = upstream_payload(context, AgentMessage("question"))
    serialized = json.dumps(payload)
    assert "_llm" not in serialized and "top-secret" not in serialized
    assert "never-export" not in serialized


def test_explainer_rejects_invented_citation():
    output = explanation()
    output["citation_ids"] = ["invented-document"]
    result = ExplainerAgent().run(context_with(ScriptedProvider(output)), AgentMessage("test"))
    assert result.error == "INVALID_OUTPUT"
    assert not result.content


def test_model_validation_errors_do_not_log_candidate_text(caplog):
    result = ExplainerAgent().run(context_with(ScriptedProvider({
        "private_clinical_marker": "PRIVATE_CANDIDATE_DO_NOT_LOG"
    })), AgentMessage("test"))
    assert result.error == "INVALID_OUTPUT"
    assert result.metadata["error_code"] == "INVALID_OUTPUT"
    assert "PRIVATE_CANDIDATE_DO_NOT_LOG" not in caplog.text


@pytest.mark.parametrize("bad", ["not JSON", {"soap": {}}, {**explanation(), "invented": True}])
def test_explainer_rejects_invalid_structured_output(bad):
    result = ExplainerAgent().run(context_with(ScriptedProvider(bad)), AgentMessage("test"))
    assert result.error


@pytest.mark.parametrize("candidate,regulation", [
    ("我将为你生成电子处方。", "nhc_2022_21"),
    ("建议你口服某药 500mg。", "nhc_2022_13"),
    ("我是你的接诊医生。", "nhc_2022_13"),
])
def test_local_rules_block_candidate_without_api(candidate, regulation):
    provider = ScriptedProvider()
    result = SafetyAgent().run(context_with(provider, candidate=candidate), AgentMessage("科普"))
    assert result.error is None
    assert result.metadata["decision"] == "block"
    assert result.metadata["regulations"][0]["id"] == regulation
    assert candidate not in result.content
    assert provider.calls == []


def test_prescription_question_does_not_block_safe_education():
    candidate = "我可以解释为什么不能生成处方，处方须由接诊医师本人开具。"
    provider = ScriptedProvider(review())
    result = SafetyAgent().run(context_with(provider, candidate=candidate),
                              AgentMessage("请帮我开个处方"))
    assert result.metadata["decision"] == "pass"
    assert candidate in result.content
    assert len(provider.calls) == 1


def test_semantic_reviewer_cannot_silently_replace_passed_candidate():
    provider = ScriptedProvider(review(approved_text="被忽略的额外文字"))
    result = SafetyAgent().run(context_with(provider, candidate="请补充症状。"), AgentMessage("test"))
    assert "请补充症状。" in result.content
    assert "被忽略" not in result.content


@pytest.mark.parametrize("error", [RuntimeError("failure"), ValueError("parse"),
                                  LLMProviderError("TIMEOUT")])
def test_safety_fails_closed_on_provider_error(error):
    result = SafetyAgent().run(context_with(ScriptedProvider(error), candidate="尚待审核"),
                              AgentMessage("test"))
    assert result.error
    assert result.metadata["decision"] == "block"
    assert result.metadata["approved_text"] == ""
    assert result.content == ""


def test_safety_unknown_regulation_fails_closed():
    provider = ScriptedProvider(review(regulation_ids=["invented-regulation"]))
    result = SafetyAgent().run(context_with(provider, candidate="尚待审核"), AgentMessage("test"))
    assert result.error and not result.metadata["approved_text"]


def test_missing_explainer_preserves_underlying_operational_error():
    context = context_with(ScriptedProvider())
    context.steps.append({"agent": "explainer", "content": "", "error": "TIMEOUT",
                          "metadata": {"error_code": "TIMEOUT"}})
    result = SafetyAgent().run(context, AgentMessage("test"))
    assert result.error == "TIMEOUT"
    assert result.metadata["error_code"] == "TIMEOUT"
    assert not result.metadata["approved_text"]


def test_safety_semantic_block_uses_only_safe_replacement():
    provider = ScriptedProvider(review("block", reasons=["需要医师核验"], severity="high",
                                      regulation_ids=["nhc_2022_13"]))
    result = SafetyAgent().run(context_with(provider, candidate="模型应拦截的候选"),
                              AgentMessage("test"))
    assert result.metadata["decision"] == "block"
    assert "模型应拦截的候选" not in result.content
    assert "不能替代" in result.content


def test_replacement_requires_independent_recheck():
    provider = ScriptedProvider(review("replace", approved_text="信息不足，请咨询医师。"), review())
    result = SafetyAgent().run(context_with(provider, candidate="原候选"), AgentMessage("test"))
    assert result.error is None and result.metadata["decision"] == "replace"
    assert result.content.startswith("信息不足，请咨询医师。")
    assert provider.calls[1]["payload"]["replacement_review"] is True


def test_unsafe_replacement_is_never_released():
    provider = ScriptedProvider(review("replace", approved_text="建议你口服某药500mg。"))
    result = SafetyAgent().run(context_with(provider, candidate="原候选"), AgentMessage("test"))
    assert result.error and not result.content


def test_emergency_precedes_missing_candidate_and_contraindications():
    context = context_with(ScriptedProvider())
    context.facts["red_flags"] = ["呼吸困难"]
    context.steps[2]["metadata"]["contraindications"] = ["test-contraindication"]
    result = SafetyAgent().run(context, AgentMessage("test"))
    assert result.error is None
    assert result.metadata["severity"] == "critical"
    assert result.metadata["escalate"] is True
    assert "120" in result.content


def test_invalid_rules_configuration_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAFETY_RULES_PATH", str(path))
    result = SafetyAgent().run(context_with(ScriptedProvider(), candidate="原候选"),
                              AgentMessage("test"))
    assert result.error and not result.content


def test_real_langgraph_detects_no_conflict_without_fake_debate():
    provider = ScriptedProvider({"conflicts": [], "summary": "未发现实际观点冲突。"})
    result = DebateAgent().run(context_with(provider), AgentMessage("test"))
    assert result.error is None
    assert result.metadata["engine"] == "langgraph"
    assert result.metadata["rounds"] == []
    assert len(provider.calls) == 1


def conflict_detection():
    return {"conflicts": [{"topic": "能否排除风险", "positions": [
        {"agent": "risk", "claim": "尚不能排除风险", "citation_ids": []},
        {"agent": "medication", "claim": "可以排除风险", "citation_ids": []},
    ]}], "summary": "测试中的待核验分歧"}


def verdict(unresolved=None):
    return {"conclusion": "保留不确定性并咨询医师", "rationale": ["缺少检查信息"],
            "unresolved": unresolved or [], "citation_ids": ["chunk-unit"],
            "requires_doctor": True}


def test_real_langgraph_runs_challenge_and_adjudication(monkeypatch):
    monkeypatch.setenv("DEBATE_MAX_ROUNDS", "1")
    provider = ScriptedProvider(conflict_detection(),
        {"challenges": ["缺少什么证据？"], "evidence_gaps": ["检查结果"]}, verdict(["待核验"]))
    result = DebateAgent().run(context_with(provider), AgentMessage("test"))
    assert result.error is None
    assert len(result.metadata["rounds"]) == 1
    assert result.metadata["verdict"]["unresolved"] == ["待核验"]
    assert len(provider.calls) == 3
    assert result.citations[0]["chunk_id"] == "chunk-unit"


def test_debate_rejects_invented_agent_positions():
    detection = conflict_detection()
    detection["conflicts"][0]["positions"][0]["claim"] = "没有上游提供的断言"
    result = DebateAgent().run(context_with(ScriptedProvider(detection)), AgentMessage("test"))
    assert result.error == "INVALID_OUTPUT"


def test_debate_skips_when_colleague_modules_not_provided():
    context = AgentContext(facts={"_llm": ScriptedProvider()})
    result = DebateAgent().run(context, AgentMessage("test"))
    assert result.error is None
    assert result.metadata["reason"] == "insufficient_upstream_data"


def test_http_client_preserves_real_usage_and_explicit_output_limit():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert json.loads(request.content)["max_tokens"] == 321
        return httpx.Response(200, json={"id": "req-real", "model": "returned-model", "choices": [
            {"message": {"content": "{\"ok\":true}"}}], "usage": {
            "prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26,
            "prompt_cache_hit_tokens": 4}})
    client = OpenAICompatibleClient("test-secret", "https://unit.invalid/v1", "model",
                                    max_tokens=321, transport=httpx.MockTransport(handler))
    response = client.complete("system", "user", agent="unit")
    assert response.usage == LLMUsage(17, 9, 26, 4)
    assert response.model == "returned-model" and response.request_id == "req-real"


def test_missing_usage_stays_unknown_instead_of_zero():
    client = OpenAICompatibleClient("secret", "https://unit.invalid/v1", "model",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [
            {"message": {"content": "answer"}}]})))
    assert client.complete("system", "user", agent="unit").usage.input_tokens is None


@pytest.mark.parametrize("status,code", [(401, "LLM_HTTP_401"), (429, "RATE_LIMITED"),
                                        (503, "LLM_PROVIDER_UNAVAILABLE")])
def test_provider_error_is_sanitized(status, code):
    client = OpenAICompatibleClient("do-not-leak", "https://unit.invalid/v1", "model", max_retries=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text="private provider body")))
    with pytest.raises(LLMProviderError) as error:
        client.complete("system", "user", agent="unit")
    assert error.value.code == code
    assert "private" not in str(error.value) and "do-not-leak" not in str(error.value)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_failure_is_never_retried_with_one_budget_reservation(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="ambiguous provider failure")
    client = OpenAICompatibleClient("secret", "https://unit.invalid/v1", "model", max_retries=4,
                                    transport=httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError, match="LLM_PROVIDER_UNAVAILABLE"):
        client.complete("system", "user", agent="unit")
    assert len(calls) == 1


def test_explicit_rate_limit_rejection_can_be_retried():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})
    client = OpenAICompatibleClient("secret", "https://unit.invalid/v1", "model", max_retries=1,
                                    transport=httpx.MockTransport(handler))
    assert client.complete("system", "user", agent="unit").content == "answer"
    assert len(calls) == 2


def test_http_configuration_uses_environment_without_echo(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LLMConfigurationError, match="LLM_NOT_CONFIGURED"):
        OpenAICompatibleClient.from_env()
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://unit.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "unit-model")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "777")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")
    client = OpenAICompatibleClient.from_env()
    assert client.max_tokens == 777 and client.timeout == 12
    assert "secret" not in repr(replace(client))


def configured_environment(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://unit.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "unit-model")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "2048")


def test_request_options_from_environment_are_passed_to_http(monkeypatch):
    configured_environment(monkeypatch)
    options = {"thinking": {"type": "disabled"}, "response_format": {"type": "json_object"},
               "reasoning_effort": "low"}
    monkeypatch.setenv("LLM_REQUEST_OPTIONS", json.dumps(options))
    def handler(request):
        payload = json.loads(request.content)
        assert all(payload[key] == value for key, value in options.items())
        assert payload["model"] == "unit-model"
        assert payload["stream"] is False
        assert payload["max_tokens"] == 2048
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    client = replace(OpenAICompatibleClient.from_env(), transport=httpx.MockTransport(handler))
    assert client.complete("system", "user", agent="unit").content == "{}"


def test_request_options_default_to_no_vendor_specific_behavior(monkeypatch):
    configured_environment(monkeypatch)
    monkeypatch.delenv("LLM_REQUEST_OPTIONS", raising=False)
    client = OpenAICompatibleClient.from_env()
    assert client.request_options == {}


@pytest.mark.parametrize("field,value", [
    ("model", "other-model"), ("messages", []), ("stream", True), ("max_tokens", 90000),
    ("max_completion_tokens", 90000), ("max_output_tokens", 90000), ("n", 9),
    ("temperature", 1), ("stream_options", {}),
])
def test_request_options_cannot_override_core_or_budget_fields(monkeypatch, field, value):
    configured_environment(monkeypatch)
    monkeypatch.setenv("LLM_REQUEST_OPTIONS", json.dumps({field: value}))
    with pytest.raises(LLMConfigurationError, match="LLM_INVALID_CONFIGURATION"):
        OpenAICompatibleClient.from_env()


@pytest.mark.parametrize("options", ["{not-json}", "[]", "null", "5", '{"x":NaN}'])
def test_invalid_request_options_fail_configuration(monkeypatch, options):
    configured_environment(monkeypatch)
    monkeypatch.setenv("LLM_REQUEST_OPTIONS", options)
    with pytest.raises(LLMConfigurationError, match="LLM_INVALID_CONFIGURATION"):
        OpenAICompatibleClient.from_env()


def test_direct_client_options_are_revalidated_before_http():
    client = OpenAICompatibleClient("secret", "https://unit.invalid/v1", "unit-model")
    client.request_options["stream"] = True
    with pytest.raises(LLMConfigurationError, match="LLM_INVALID_CONFIGURATION"):
        client.complete("system", "user", agent="unit")
