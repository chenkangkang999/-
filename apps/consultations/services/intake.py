"""Patient-facing intake gate; the teammate Coordinator remains replaceable."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

from agents.base.agent import AgentResult
from agents.base.message import AgentMessage
from agents.llm.support import complete_json, sanitized_error_code
from apps.consultations.models import ConsultationRun
from apps.consultations.services.events import publish

logger = logging.getLogger(__name__)
FIELDS = ("age", "duration", "allergies", "current_medications", "chronic_conditions", "associated_symptoms")


def enabled():
    return getattr(settings, "CLINICAL_INTAKE_ENABLED", True)


def policy():
    path = Path(os.getenv("CLINICAL_INTAKE_POLICY_PATH", str(settings.BASE_DIR / "configs" / "clinical_intake.json")))
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    result = json.loads(path.read_text(encoding="utf-8"))
    if not set(result["required_fields"]).issubset(FIELDS) or not result["required_fields"]:
        raise ValueError("INVALID_INTAKE_POLICY")
    return result


class IntakeFact(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    field: Literal["age", "duration", "allergies", "current_medications", "chronic_conditions", "associated_symptoms"]
    value: str = Field(min_length=1, max_length=500)
    source_text: str = Field(min_length=1, max_length=1000)


class IntakeExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[IntakeFact] = Field(max_length=6)


def red_flags(text, rules):
    flags = []
    for pattern in rules["red_flag_patterns"]:
        for match in re.finditer(pattern, text):
            before = text[max(0, match.start() - 14):match.start()]
            before = re.split(rules["contrast_pattern"], before)[-1]
            negated = re.search(rules["negation_pattern"], before)
            exception = re.search(rules["negation_exception_pattern"], before)
            if not negated or exception:
                flags.append(match.group())
                break
    return list(dict.fromkeys(flags))


def rule_facts(text):
    patterns = {
        "age": r"\d{1,3}\s*岁",
        "duration": r"(?:持续|已经|大约|约)?[一二两三四五六七八九十半\d]+(?:个)?(?:小时|天|周|月|年)",
        "allergies": r"(?:无|没有|否认)(?:已知)?(?:药物)?过敏(?:史)?",
        "current_medications": r"(?:未|没有|无)(?:正在)?(?:用药|服药|使用药物)",
        "chronic_conditions": r"(?:无|没有|否认)(?:已知)?(?:基础疾病|慢性病|慢病)",
    }
    return {field: match.group() for field, pattern in patterns.items() if (match := re.search(pattern, text))}


class PipelineTracker:
    def __init__(self, run):
        self.run = run
        self.lock = threading.RLock()
        self.states = {}
        self.value = {"stages": [{**s, "status": "pending"} for s in policy()["stages"]], "current_stage": "precheck", "reason": ""}
        self.save()

    def save(self):
        self.value["updated_at"] = timezone.now().isoformat()
        self.run.metadata["pipeline"] = deepcopy(self.value)
        ConsultationRun.objects.filter(pk=self.run.pk).update(metadata=self.run.metadata)
        publish(self.run.consultation_id, run_id=self.run.pk, trace_id=self.run.trace_id,
                event_type="pipeline.updated", payload={"pipeline": deepcopy(self.value)})

    def stage(self, stage_id, status, reason=""):
        with self.lock:
            for stage in self.value["stages"]:
                if stage["id"] == stage_id:
                    stage.update(status=status, reason=reason)
            active = next((s for s in self.value["stages"] if s["status"] in {"running", "waiting"}), None)
            self.value["current_stage"] = active["id"] if active else stage_id
            self.value["reason"] = reason
            self.save()

    def agent(self, agent, status):
        with self.lock:
            self.states[agent] = status
            for stage in self.value["stages"]:
                if agent not in stage["agents"]:
                    continue
                values = [self.states.get(name) for name in stage["agents"]]
                terminal = all(v in {"completed", "skipped"} for v in values)
                state = "failed" if "failed" in values else ("skipped" if terminal and all(v == "skipped" for v in values) else "completed" if terminal else "running")
                self.stage(stage["id"], state, "上游实际意见不足，未进行质证" if state == "skipped" and agent == "debate" else "")

    def finish(self, failed=False):
        with self.lock:
            waiting = self.run.metadata.get("intake", {}).get("status") == "awaiting_information"
            for stage in self.value["stages"]:
                if failed and stage["status"] == "running":
                    stage.update(status="failed", reason="本轮执行失败")
                elif stage["status"] == "pending" and not waiting:
                    stage.update(status="skipped", reason="本轮未执行此步骤")
            if waiting:
                for stage in self.value["stages"]:
                    if stage["id"] == "intake":
                        stage.update(status="waiting", reason="等待用户补充病史")
                self.value.update(current_stage="intake", reason="等待用户补充病史")
            self.save()


def route_turn(run, context, provider):
    rules = policy()
    tracker = context.facts["_pipeline_tracker"]
    tracker.stage("precheck", "running")
    submission = run.metadata.get("intake_submission", {})
    previous = run.consultation.runs.exclude(pk=run.pk).filter(status__in=["succeeded", "blocked"]).order_by("-created_at").first()
    previous_intake = previous.metadata.get("intake", {}) if previous else {}
    from apps.consultations.services.clinical_evidence import policy as clinical_policy
    from apps.consultations.services.clinical_risk import news2
    from apps.consultations.services.clinical_schema import input_schema
    permitted_fields = set(FIELDS) | {f["id"] for f in input_schema()["fields"]}
    education = bool(re.search(rules["education_pattern"], run.message.content.strip())
                     and not re.search(rules["personal_pattern"], run.message.content)
                     and not submission and not previous_intake.get("answers"))
    screen_text = run.message.content + "\n" + "\n".join(str(v) for v in submission.values())
    flags = [] if education else red_flags(screen_text, rules)
    measured = news2({**context.patient, **previous_intake.get("answers", {}), **submission}, clinical_policy())
    if not education and measured.get("risk_level") in {"high", "critical"}:
        flags.append("已填报生命体征触发急性病情高优先级警报")
    if previous_intake.get("status") == "emergency":
        flags = list(dict.fromkeys(flags + previous_intake.get("red_flags", ["前轮紧急风险尚未解除"])))
    tracker.stage("precheck", "completed", "发现急症线索，优先提供急诊指引" if flags else "未在本次描述中发现配置的急症词；不能排除临床风险")
    answers = {k: v for k, v in (previous.metadata.get("intake", {}).get("answers", {}) if previous else {}).items() if k in permitted_fields and isinstance(v, (str, int, float, bool))}
    tracker.stage("intake", "running")
    user_texts = [m["content"] for m in context.facts.get("history", []) if m.get("role") == "user"] + [run.message.content]
    # The latest confirmed snapshot wins over older free-text denials.
    # Replaying every old message here could erase a newly reported allergy.
    answers.update(rule_facts(run.message.content))
    extraction_status = "structured_or_rules"
    mode = getattr(settings, "CLINICAL_INTAKE_EXTRACTOR", os.getenv("CLINICAL_INTAKE_EXTRACTOR", "rules"))
    if not flags and not education and mode == "llm" and not submission:
        try:
            extracted, _ = complete_json(context, "triage", "intake", {"user_messages": user_texts, "allowed_fields": list(FIELDS)}, IntakeExtraction)
            for fact in extracted.facts:
                current_quote = fact.source_text in run.message.content
                historical_gap = fact.field not in answers and any(fact.source_text in text for text in user_texts)
                if (current_quote or historical_gap) and fact.value in fact.source_text:
                    answers[fact.field] = fact.value
            extraction_status = "llm_verified_quotes"
        except Exception as exc:
            extraction_status = "failed"
            logger.warning("Intake extraction failed code=%s", sanitized_error_code(exc))
    answers.update({k: v.strip() if isinstance(v, str) else v for k, v in submission.items()
                    if k in permitted_fields and (not isinstance(v, str) or v.strip())})
    missing = [] if education else [name for name in rules["required_fields"] if not answers.get(name)]
    questions = [{"field": name, **rules["fields"][name]} for name in missing[:rules["max_questions_per_turn"]]]
    intake = {"status": "emergency" if flags else ("awaiting_information" if missing else "ready"),
              "answers": answers, "missing_fields": missing, "questions": questions,
              "summary": "已记录主诉与已明确提供的病史；未提供的信息保持未知。", "extraction_status": extraction_status,
              "policy_version": rules["version"]}
    intake.update(red_flags=flags, intent="education" if education else "personal_consultation")
    run.metadata["intake"] = intake
    context.facts["_screened_red_flags"] = flags
    context.facts["_clinical_intake_ready"] = not missing and not flags
    context.facts["intake"] = intake
    # Keep the teammate patient contract (list-valued allergies/medications) intact.
    # Providers can prioritize this explicit, current, quoted history over profiles.
    context.patient["reported_history"] = deepcopy(answers)
    ConsultationRun.objects.filter(pk=run.pk).update(metadata=run.metadata)
    if flags or missing:
        from agents.base.registry import get_agent, load_all

        load_all()
        context.facts["red_flags"] = flags
        candidate = rules["followup_intro"] + "\n" + "\n".join(f"{i + 1}. {q['question']}" for i, q in enumerate(questions))
        context.record("triage", AgentResult(agent="triage", content=candidate,
                       metadata={"need_followup": bool(missing), "red_flags": flags}).to_dict())
        context.facts["candidate_text"] = candidate
        if missing and not flags:
            tracker.stage("intake", "waiting", "等待用户补充病史")
        get_agent("safety").run(context, AgentMessage(content=run.message.content))
        return SimpleNamespace(steps=context.steps, risk_level="critical" if flags else "unknown")
    tracker.stage("intake", "completed")
    result = provider.run(run.message.content, context, enable_debate=settings.ENABLE_DEBATE)
    if education:
        tracker.stage("intake", "skipped", "一般健康知识查询，无需采集个人病史")
    return result
