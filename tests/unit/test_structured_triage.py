from __future__ import annotations

import csv
import json

import pytest

from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.contracts import LLMResponse, LLMUsage
from agents.specialists.triage import TriageAgent
from apps.consultations.services.terminology import probabilities, standardize


class TestModel:
    def __init__(self, output):
        self.output = output

    def complete(self, *args, **kwargs):
        return LLMResponse(json.dumps(self.output, ensure_ascii=False), LLMUsage(1, 1, 2), "explicit-test")


def assessment(**updates):
    return {"chief_complaint": "咳嗽三天", "symptoms": [{"name": "咳嗽", "source_text": "咳嗽三天", "status": "present"}],
            "differentials": [{"label": "待核验的测试方向", "rationale": "测试描述不足", "missing_evidence": ["临床检查"]}], **updates}


def test_triage_uses_explicit_sources_and_no_invented_codes_or_probabilities():
    context = AgentContext(facts={"_llm": TestModel(assessment())})
    result = TriageAgent().run(context, AgentMessage(content="咳嗽三天"))
    assert not result.error
    assert result.metadata["differentials"][0]["probability"] is None
    assert result.metadata["coding"]["status"] == "not_connected"
    assert result.metadata["coding"]["concepts"] == []
    assert "不是确诊" in result.content


def test_triage_rejects_assistant_only_symptom_and_subjective_percentages():
    result = TriageAgent().run(AgentContext(facts={"_llm": TestModel(assessment(symptoms=[{"name": "发热", "source_text": "发热"}]))}), AgentMessage(content="咳嗽三天"))
    assert result.error == "INVALID_OUTPUT"
    output = assessment(differentials=[{"label": "测试疾病90%", "rationale": "不能给百分比", "missing_evidence": []}])
    assert TriageAgent().run(AgentContext(facts={"_llm": TestModel(output)}), AgentMessage(content="咳嗽三天")).error


def test_denied_symptom_is_not_standardized_as_positive():
    output = assessment(symptoms=[{"name": "胸痛", "source_text": "没有胸痛", "status": "denied"}])
    result = TriageAgent().run(AgentContext(facts={"_llm": TestModel(output)}), AgentMessage(content="咳嗽三天，没有胸痛"))
    assert not result.error
    assert result.metadata["symptoms"] == []
    assert result.metadata["symptom_states"][0]["status"] == "denied"


def test_terminology_only_maps_imported_system_and_exact_alias(tmp_path):
    path = tmp_path / "terms.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["system", "code", "name", "source", "synonyms", "version"])
        writer.writeheader()
        writer.writerow({"system": "ICD-10", "code": "TEST", "name": "测试症状", "source": "https://example.test/catalog", "synonyms": "测试别名", "version": "test"})
    result = standardize(["测试别名", "未知症状"], {"coding_catalog": str(path), "coding_systems": ["ICD-10", "ICD-11"]})
    assert result["concepts"][0]["system"] == "ICD-10"
    assert result["unmapped"] == ["未知症状"]


@pytest.mark.parametrize("invalid", [[1.2], [float("nan")], [True], [], [0.7, 0.7]])
def test_external_probability_provider_cannot_skip_calibration_validation(monkeypatch, invalid):
    import apps.consultations.services.terminology as terms
    class Provider:
        def predict(self, **kwargs):
            return {"probabilities": invalid, "model_id": "test", "calibration_reference": "https://example.test/test", "population": "test-only", "model_sha256": "test-only"}
    monkeypatch.setattr(terms, "import_string", lambda _: Provider)
    with pytest.raises(ValueError):
        probabilities(AgentContext(), [{}], {"probability_provider": "test.Provider"})
