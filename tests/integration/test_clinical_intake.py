from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agents.base.agent import AgentResult
from agents.specialists.debate_agent import DebateAgent
from agents.specialists.explainer import ExplainerAgent
from agents.specialists.safety import SafetyAgent
from apps.consultations.models import Consultation, ConsultationRun, Message
from apps.consultations.services import coordinator as service
from apps.consultations.services.intake import IntakeExtraction, policy, red_flags

pytestmark = pytest.mark.django_db(transaction=True)

COMPLETE = {"age": "27岁", "duration": "三天", "allergies": "无药物过敏史",
            "current_medications": "没有用药", "chronic_conditions": "无基础疾病"}


@pytest.fixture(autouse=True)
def intake_settings(settings):
    settings.CLINICAL_INTAKE_ENABLED = True
    settings.CLINICAL_INTAKE_EXTRACTOR = "rules"


def consultation(client):
    return client.post("/api/v1/consultations/", {"title": "多轮接诊测试"}, format="json").json()["id"]


def post(client, cid, text, **extra):
    return client.post(f"/api/v1/consultations/{cid}/messages/", {"content": text, **extra}, format="json")


def approve_questions(monkeypatch):
    def execute(self, context, message):
        return AgentResult(agent="safety", content=context.facts.get("candidate_text", "已审核健康指引"),
                           metadata={"decision": "pass", "severity": "low", "reasons": [],
                                     "approved_text": context.facts.get("candidate_text", "已审核健康指引")})
    monkeypatch.setattr(SafetyAgent, "_execute", execute)


def no_coordinator(monkeypatch):
    called = Mock(side_effect=AssertionError("Information gate must stop the Coordinator"))
    original = service.import_string
    monkeypatch.setattr(service, "import_string", lambda path: (lambda: SimpleNamespace(run=called))
                        if path == "agents.base.coordinator.Coordinator" else original(path))
    return called


def test_missing_information_stops_downstream_and_persists_waiting(auth_client, monkeypatch):
    approve_questions(monkeypatch)
    called = no_coordinator(monkeypatch)
    cid = consultation(auth_client)
    response = post(auth_client, cid, "咳嗽")
    assert response.status_code == 201
    data = response.json()
    assert data["intake"]["status"] == "awaiting_information"
    assert "age" in data["intake"]["missing_fields"]
    assert len(data["intake"]["questions"]) == 3
    assert "暂不进入用药建议" in data["reply"]["content"]
    assert [s["agent"] for s in data["steps"]] == ["triage", "safety"]
    assert next(s for s in data["pipeline"]["stages"] if s["id"] == "intake")["status"] == "waiting"
    assert next(s for s in data["pipeline"]["stages"] if s["id"] == "retrieval")["status"] == "pending"
    called.assert_not_called()
    restored = auth_client.get(f"/api/v1/consultations/{cid}/runs/{data['run_id']}/").json()
    assert restored["pipeline"] == data["pipeline"]


def test_multiturn_answers_continue_existing_coordinator_and_preserve_negation(auth_client, monkeypatch):
    approve_questions(monkeypatch)
    import agents.specialists.triage as triage
    from agents.contracts import LLMResponse, LLMUsage
    from agents.specialists.retrieval import RetrievalAgent
    monkeypatch.setattr(RetrievalAgent, "_execute", lambda self, context, message:
                        AgentResult(agent="retrieval", content="测试未命中", metadata={"status": "no_hits", "hits": 0}))
    monkeypatch.setattr(triage, "complete_json", lambda *args: (triage.TriageOutput(
        chief_complaint="咳嗽三天", symptoms=[{"name": "咳嗽", "source_text": "咳嗽"}], differentials=[]),
        LLMResponse("{}", LLMUsage(1, 1, 2), "test-triage")))
    monkeypatch.setattr(ExplainerAgent, "_execute", lambda self, context, message:
                        AgentResult(agent="explainer", content="信息已齐，请由医生结合检查确认。"))
    monkeypatch.setattr(DebateAgent, "_execute", lambda self, context, message:
                        AgentResult(agent="debate", content="无足够意见形成分歧", metadata={"status": "skipped"}))
    cid = consultation(auth_client)
    first = post(auth_client, cid, "27岁，咳嗽三天，无药物过敏史").json()
    assert first["intake"]["status"] == "awaiting_information"
    second = post(auth_client, cid, "没有胸痛，也没有呼吸困难。没有用药，无基础疾病")
    assert second.status_code == 201
    data = second.json()
    assert data["intake"]["status"] == "ready"
    assert data["intake"]["answers"]["age"] == "27岁"
    assert {s["agent"] for s in data["steps"]} == {"triage", "retrieval", "risk", "medication", "debate", "explainer", "safety"}
    assert Consultation.objects.get(pk=cid).risk_level == "unknown"
    assert all(s["status"] == ("skipped" if s["id"] == "debate" else "completed") for s in data["pipeline"]["stages"])
    assert next(s for s in data["steps"] if s["agent"] == "debate")["status"] == "skipped"
    assert Message.objects.filter(consultation_id=cid, role="user").count() == 2


def test_structured_intake_can_complete_without_semantic_extraction(auth_client, monkeypatch):
    approve_questions(monkeypatch)
    original = service.import_string
    called = Mock()

    class Provider:
        def run(self, text, context, enable_debate=True):
            called()
            context.facts["candidate_text"] = "已审核健康指引"
            SafetyAgent().run(context, SimpleNamespace(content=text))
            return SimpleNamespace(steps=context.steps, risk_level="low")

    monkeypatch.setattr(service, "import_string", lambda path: Provider if path == "agents.base.coordinator.Coordinator" else original(path))
    response = post(auth_client, consultation(auth_client), "咳嗽", intake=COMPLETE)
    assert response.status_code == 201
    assert response.json()["intake"]["status"] == "ready"
    called.assert_called_once()


def test_emergency_exits_before_history_completion_and_paid_calls(auth_client, monkeypatch):
    no_coordinator(monkeypatch)
    import agents.specialists.safety as safety
    monkeypatch.setattr(safety, "complete_json", Mock(side_effect=AssertionError("No paid emergency call")))
    response = post(auth_client, consultation(auth_client), "突然胸痛，而且呼吸困难")
    assert response.status_code == 201
    data = response.json()
    assert data["intake"]["status"] == "emergency"
    assert "120" in data["reply"]["content"]
    assert "暂不进入用药建议" not in data["reply"]["content"]
    run = ConsultationRun.objects.select_related("consultation").get(pk=data["run_id"])
    assert run.consultation.status == "escalated"
    assert next(s for s in data["pipeline"]["stages"] if s["id"] == "retrieval")["status"] == "skipped"


@pytest.mark.parametrize("text,expected", [("没有胸痛", []), ("否认呼吸困难", []),
    ("没有胸痛，但现在呼吸困难", ["呼吸困难"]), ("没有胸痛但现在呼吸困难", ["呼吸困难"]),
    ("不能否认胸痛", ["胸痛"]), ("不是没有胸痛", ["胸痛"]), ("胸痛伴晕厥", ["胸痛", "晕厥"])])
def test_red_flag_negation(text, expected):
    assert red_flags(text, policy()) == expected


def test_semantic_extraction_rejects_quotes_from_assistant_or_other_sources(auth_client, monkeypatch, settings):
    settings.CLINICAL_INTAKE_EXTRACTOR = "llm"
    approve_questions(monkeypatch)
    no_coordinator(monkeypatch)
    import apps.consultations.services.intake as intake
    monkeypatch.setattr(intake, "complete_json", lambda *args: (IntakeExtraction(facts=[
        {"field": "age", "value": "30岁", "source_text": "30岁"},
        {"field": "duration", "value": "三天", "source_text": "咳嗽三天"},
    ]), None))
    result = post(auth_client, consultation(auth_client), "咳嗽三天").json()
    assert "age" in result["intake"]["missing_fields"]
    assert result["intake"]["answers"]["duration"] == "三天"


def test_same_request_key_cannot_change_structured_answers(auth_client):
    cid = consultation(auth_client)
    key = str(uuid.uuid4())
    c = Consultation.objects.get(pk=cid)
    service.create_run(c, "咳嗽", uuid.UUID(key), intake={"age": "27岁"})
    response = auth_client.post(f"/api/v1/consultations/{cid}/runs/", {
        "content": "咳嗽", "client_request_id": key, "intake": {"age": "28岁"}}, format="json")
    assert response.status_code == 409


def test_intake_payload_is_validated(auth_client):
    response = post(auth_client, consultation(auth_client), "咳嗽", intake={"age": "x" * 501})
    assert response.status_code == 400


def test_emergency_in_structured_fields_is_not_bypassed(auth_client, monkeypatch):
    no_coordinator(monkeypatch)
    response = post(auth_client, consultation(auth_client), "补充信息", intake={**COMPLETE, "associated_symptoms": "突然呼吸困难"})
    assert response.json()["intake"]["status"] == "emergency"
    assert "120" in response.json()["reply"]["content"]


def test_unresolved_emergency_remains_priority_in_next_turn(auth_client, monkeypatch):
    no_coordinator(monkeypatch)
    cid = consultation(auth_client)
    assert post(auth_client, cid, "胸痛伴晕厥").status_code == 201
    response = post(auth_client, cid, "先帮我开药吧", intake=COMPLETE)
    assert response.json()["intake"]["status"] == "emergency"
    assert "120" in response.json()["reply"]["content"]


@pytest.mark.parametrize("mode", ["rules", "llm"])
def test_new_allergy_is_not_erased_by_older_free_text_denial(auth_client, monkeypatch, settings, mode):
    settings.CLINICAL_INTAKE_EXTRACTOR = mode
    approve_questions(monkeypatch)
    no_coordinator(monkeypatch)
    import apps.consultations.services.intake as intake
    monkeypatch.setattr(intake, "complete_json", lambda *args: (IntakeExtraction(facts=[
        {"field": "allergies", "value": "无药物过敏史", "source_text": "无药物过敏史"},
    ]), None))
    cid = consultation(auth_client)
    post(auth_client, cid, "27岁，咳嗽三天，无药物过敏史")
    second = post(auth_client, cid, "补充过敏史", intake={"allergies": "青霉素过敏"}).json()
    assert second["intake"]["answers"]["allergies"] == "青霉素过敏"
    third = post(auth_client, cid, "补充一下症状变化").json()
    assert third["intake"]["answers"]["allergies"] == "青霉素过敏"


def test_general_education_does_not_require_personal_history(auth_client, monkeypatch, settings):
    settings.CLINICAL_INTAKE_EXTRACTOR = "llm"
    approve_questions(monkeypatch)
    original = service.import_string

    class Provider:
        def run(self, text, context, enable_debate=True):
            assert isinstance(context.patient.get("allergies"), list)
            assert "reported_history" in context.patient
            context.facts["candidate_text"] = "已审核的健康知识"
            SafetyAgent().run(context, SimpleNamespace(content=text))
            return SimpleNamespace(steps=context.steps, risk_level="low")

    monkeypatch.setattr(service, "_patient_facts", lambda _: {"allergies": [], "current_medications": []})
    monkeypatch.setattr(service, "import_string", lambda path: Provider if path == "agents.base.coordinator.Coordinator" else original(path))
    import apps.consultations.services.intake as intake
    monkeypatch.setattr(intake, "complete_json", Mock(side_effect=AssertionError("Education does not collect personal facts")))
    data = post(auth_client, consultation(auth_client), "什么是高血压").json()
    assert data["intake"]["intent"] == "education"
    assert data["intake"]["missing_fields"] == []
    assert next(s for s in data["pipeline"]["stages"] if s["id"] == "intake")["status"] == "skipped"


def test_telemetry_failure_cannot_prevent_terminal_failure(auth_client, monkeypatch):
    approve_questions(monkeypatch)
    original = service.import_string

    class Provider:
        def run(self, *args, **kwargs):
            raise ValueError("DO_NOT_PERSIST_INTERNAL_CANDIDATE")

    monkeypatch.setattr(service, "import_string", lambda path: Provider if path == "agents.base.coordinator.Coordinator" else original(path))
    from apps.consultations.services.intake import PipelineTracker
    monkeypatch.setattr(PipelineTracker, "finish", Mock(side_effect=RuntimeError("telemetry unavailable")))
    data = post(auth_client, consultation(auth_client), "咳嗽", intake=COMPLETE).json()
    run = ConsultationRun.objects.get(pk=data["run_id"])
    assert run.status == "failed"
    assert run.reply_id is None
    assert "DO_NOT_PERSIST" not in str(data)


def test_measured_critical_vitals_exit_before_retrieval(auth_client, monkeypatch):
    no_coordinator(monkeypatch)
    data = post(auth_client, consultation(auth_client), "补充实际测量值（合成测试）", intake={
        **COMPLETE, "sex": "male", "respiratory_rate": 25, "oxygen_saturation": 91,
        "supplemental_oxygen": True, "systolic_bp": 120, "heart_rate": 80,
        "consciousness": "alert", "temperature": 36.5}).json()
    assert data["intake"]["status"] == "emergency"
    assert "120" in data["reply"]["content"]


def test_schema_and_optional_false_are_not_assumed_normal(auth_client, monkeypatch):
    approve_questions(monkeypatch)
    no_coordinator(monkeypatch)
    schema = auth_client.get("/api/v1/clinical/schema/")
    assert schema.status_code == 200
    assert any(f["id"] == "current_smoker" for f in schema.json()["fields"])
    data = post(auth_client, consultation(auth_client), "咳嗽", intake={"current_smoker": False}).json()
    assert data["intake"]["answers"]["current_smoker"] is False
    assert "pregnancy" not in data["intake"]["answers"]
