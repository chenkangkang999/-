from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml

from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.specialists.medication import MedicationAgent
from agents.specialists.risk import RiskAgent
from apps.consultations.services import clinical_evidence as evidence
from apps.consultations.services.clinical_risk import framingham, news2


@pytest.fixture
def clinical_files(tmp_path, monkeypatch):
    original = evidence.policy()
    cfg = json.loads(json.dumps(original))
    cfg["data_root"] = str(tmp_path / "data")
    cfg["index_path"] = str(tmp_path / "evidence.sqlite3")
    cfg["framingham"]["artifact"] = str(evidence.project_path(original["framingham"]["artifact"]))
    cfg["drug_sources"] = [cfg["drug_sources"][0]]
    root = Path(cfg["data_root"])
    (root / "drugs").mkdir(parents=True)
    (root / "clinical").mkdir()
    drug = root / cfg["drug_sources"][0]["path"]
    with drug.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "aliases", "english_name"])
        writer.writerows([["测试药甲", "甲片", "DrugA"], ["测试药乙", "乙片", "DrugB"], ["测试药丙", "丙片", "DrugC"]])
    ddi = root / cfg["ddi"]["path"]
    with ddi.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Drug_A", "Drug_B", "Level", "Description"])
        writer.writerows([["DrugA", "DrugB", "Minor", "synthetic minor"], ["DrugB", "DrugA", "Major", "synthetic major"]])
    label = root / cfg["guidelines"]["path"]
    source = {"title": "合成测试证据（仅测试）", "url": "https://example.org/clinical-test", "authority": "drug_label", "verified": True, "reviewed_by": "unit-test", "reviewed_at": "2026-11-01"}
    label.write_text(json.dumps({"source": source, "entries": [{"id": "synthetic-a", "drug_name": "测试药甲", "aliases": ["DrugA"], "condition_terms": ["测试症状"], "evidence_text": "synthetic reference", "line": "first", "allergen_terms": ["测试类药物"], "education": ["测试用药教育", "每日3次500mg"], "adverse_effects": ["测试不良反应提醒"], "special_populations": {"pregnancy": {"status": "contraindicated", "note": "合成测试妊娠禁忌"}, "renal_impairment": {"status": "requires_doctor", "note": "合成测试肾功能核验"}}, "contraindications": [{"field": "hepatic_impairment", "equals": True, "reason": "合成测试肝病禁忌"}]}]}, ensure_ascii=False), encoding="utf-8")
    path = tmp_path / "clinical.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("CLINICAL_DATA_POLICY_PATH", str(path))
    monkeypatch.setenv("CLINICAL_DATA_ROOT", str(root))
    monkeypatch.setenv("CLINICAL_DATA_INDEX", cfg["index_path"])
    return cfg, root, label


def test_missing_structured_assets_dont_claim_safety(clinical_files):
    result = MedicationAgent()._execute(AgentContext(patient={"current_medications": ["DrugA", "DrugB"]}), AgentMessage(content="测试症状"))
    assert result.metadata["interaction_status"] == "not_connected"
    assert result.metadata["source_options"] == []
    assert "不生成药名或剂量" in result.content


def test_ddi_unordered_pair_keeps_highest_severity_and_maps_chinese(clinical_files):
    summary = evidence.import_evidence()
    assert summary["ddi"]["rows"] == 2 and summary["ddi"]["deduplicated_pairs"] == 1
    result = MedicationAgent()._execute(AgentContext(patient={"current_medications": ["甲片", "DrugB"], "allergies": []}), AgentMessage(content="测试症状"))
    assert result.metadata["interactions"][0]["severity"] == "major"
    assert result.metadata["contraindications"]
    assert result.metadata["source_options"] == []
    assert all(item["url"].startswith("https://") for item in result.citations)


def test_connected_ddi_no_hit_is_not_no_interaction(clinical_files):
    evidence.import_evidence()
    result = MedicationAgent()._execute(AgentContext(patient={"current_medications": ["DrugB", "DrugC"], "allergies": []}), AgentMessage(content=""))
    assert result.metadata["interaction_status"] == "no_hit"
    assert "不等于不存在相互作用" in result.content
    unknown = MedicationAgent()._execute(AgentContext(patient={"current_medications": ["unmapped-brand", "DrugC"]}), AgentMessage(content=""))
    assert unknown.metadata["interaction_status"] == "unmapped_drug"


def test_allergy_and_latest_history_override_older_profile(clinical_files):
    evidence.import_evidence()
    context = AgentContext(patient={"allergies": [], "current_medications": ["DrugA"], "reported_history": {"allergies": "对测试类药物过敏"}})
    result = MedicationAgent()._execute(context, AgentMessage(content="测试症状"))
    assert result.metadata["blocked_drugs"] == ["测试药甲"]
    assert not result.metadata["source_options"]
    context.facts["intake"] = {"answers": {"allergies": "无药物过敏史", "current_medications": "无"}}
    result = MedicationAgent()._execute(context, AgentMessage(content="测试症状"))
    assert not result.metadata["blocked_drugs"]
    assert result.metadata["source_options"][0]["line"] == "first"
    assert "500mg" not in result.content and "500mg" not in str(result.metadata)


def test_special_populations_block_or_require_checks_without_doses(clinical_files):
    evidence.import_evidence()
    for field in ("pregnancy", "hepatic_impairment"):
        result = MedicationAgent()._execute(AgentContext(patient={field: True}), AgentMessage(content="测试症状"))
        assert result.metadata["blocked_drugs"] == ["测试药甲"]
    result = MedicationAgent()._execute(AgentContext(patient={"renal_impairment": True, "age": "10岁"}), AgentMessage(content="测试症状"))
    checks = result.metadata["special_population_checks"]
    assert any(item["population"] == "renal_impairment" and item["status"] == "requires_doctor" for item in checks)
    assert any(item["population"] == "pediatric" for item in checks)
    assert result.metadata["dose_status"] == "withheld_requires_clinician"


def test_unreviewed_guideline_and_stale_sources_are_not_used(clinical_files):
    _, _, label = clinical_files
    evidence.import_evidence()
    value = json.loads(label.read_text(encoding="utf-8"))
    value["source"]["verified"] = False
    label.write_text(json.dumps(value), encoding="utf-8")
    result = MedicationAgent()._execute(AgentContext(), AgentMessage(content="测试症状"))
    assert not result.metadata["source_options"]
    assert "stale_requires_sync" in result.metadata["data_status"].values()
    with pytest.raises(ValueError, match="NOT_REVIEWED"):
        evidence.import_evidence()


def cvd_case(**updates):
    return {"age": 53, "sex": "male", "total_cholesterol": 161, "hdl_cholesterol": 55, "cholesterol_unit": "mg/dL", "systolic_bp": 125, "bp_treated": True, "current_smoker": False, "diabetes": True, "prior_cvd": False, **updates}


def test_original_fhs_published_case_not_invented_diagnosis_probability(clinical_files):
    result = framingham(cvd_case(), evidence.policy())
    assert result["status"] == "calculated"
    assert result["risk_percent"] == pytest.approx(15.6, abs=0.1)
    assert result["locally_calibrated"] is False and result["diagnostic_probability"] is False
    assert "general CVD" in result["endpoint"] and "TenYearCHD" in result["endpoint"]


@pytest.mark.parametrize("changes,status", [({"age": 29}, "outside_population"), ({"age": 75}, "outside_population"), ({"prior_cvd": True}, "outside_population"), ({"cholesterol_unit": "mmol/L"}, "unit_mismatch"), ({"total_cholesterol": 0}, "invalid_input"), ({"bp_treated": "unknown"}, "invalid_input"), ({"current_smoker": None}, "insufficient_data")])
def test_fhs_population_missing_fields_and_units_do_not_make_up_score(clinical_files, changes, status):
    result = framingham(cvd_case(**changes), evidence.policy())
    assert result["status"] == status and result["risk_fraction"] is None


def news_case(**updates):
    return {"age": 45, "sex": "male", "respiratory_rate": 16, "oxygen_saturation": 98, "supplemental_oxygen": False, "systolic_bp": 120, "heart_rate": 80, "consciousness": "alert", "temperature": 36.5, **updates}


def test_news2_exact_thresholds_and_no_partial_aggregate(clinical_files):
    rules = evidence.policy()
    assert news2(news_case(), rules)["score"] == 0
    total = news2(news_case(respiratory_rate=25, oxygen_saturation=91, supplemental_oxygen=True), rules)
    assert total["score"] == 8 and total["risk_level"] == "critical"
    partial = news2({"age": 45, "respiratory_rate": 25}, rules)
    assert partial["score"] is None and partial["observed_warning_level"] == "medium"
    assert news2(news_case(age=12), rules)["status"] == "outside_population"
    assert news2(news_case(pregnancy=True), rules)["status"] == "outside_population"
    assert news2(news_case(hypercapnic_respiratory_failure=True), rules)["status"] == "outside_population"


def test_extreme_risk_wins_over_chronic_calculation_and_negation(clinical_files):
    context = AgentContext(patient=cvd_case(), facts={"_screened_red_flags": ["呼吸困难"]})
    result = RiskAgent()._execute(context, AgentMessage(content="呼吸困难"))
    assert result.metadata["risk_level"] == "critical" and "120" in result.content
    assert result.metadata["chronic_risk"]["status"] == "calculated"
    assert result.metadata["diagnostic_opinions"] == []
    negative = RiskAgent()._execute(AgentContext(), AgentMessage(content="没有胸痛，也没有呼吸困难"))
    assert negative.metadata["red_flags"] == []
    assert negative.metadata["news2"]["score"] is None
    assert negative.metadata["chronic_risk"]["risk_fraction"] is None
