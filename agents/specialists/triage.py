from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register
from agents.llm.support import (
    complete_json,
    emit_started,
    failure_result,
    response_metadata,
    upstream_payload,
)


class Symptom(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    source_text: str = Field(min_length=1, max_length=1000)
    status: Literal["present", "denied", "uncertain"] = "present"


class Differential(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=1000)
    missing_evidence: list[str]


class TriageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    chief_complaint: str = Field(min_length=1, max_length=2000)
    symptoms: list[Symptom] = Field(max_length=30)
    differentials: list[Differential] = Field(max_length=20)


@register
class TriageAgent(BaseAgent):
    name = "triage"
    description = "多轮病史、带原文依据的症状整理、真实术语映射与待核验鉴别方向"
    system_prompt = "agents/prompts/triage_structured.md"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        emit_started(context, self.name)
        try:
            from apps.consultations.services.intake import policy, red_flags
            from apps.consultations.services.terminology import (
                probabilities,
                standardize,
                triage_config,
            )

            cfg = triage_config()
            intake = context.facts.get("intake", {})
            education = intake.get("intent") == "education"
            texts = [m["content"] for m in context.facts.get("history", []) if m.get("role") == "user"]
            texts += [message.content, *(str(v) for v in intake.get("answers", {}).values())]
            flags = context.facts.get("_screened_red_flags")
            if flags is None:
                flags = red_flags(message.content, policy())
            context.facts["red_flags"] = flags
            if flags:
                context.facts["chief_complaint"] = message.content
                return AgentResult(agent=self.name, content="发现急症线索，优先进行紧急风险评估。", metadata={"red_flags": flags, "need_followup": False, "diagnostic_opinions": [], "status": "urgent"})
            output, response = complete_json(context, self.name, "triage_structured", upstream_payload(context, message), TriageOutput)
            if any(not any(symptom.source_text in text for text in texts if isinstance(text, str)) for symptom in output.symptoms):
                raise ValueError("UNSUPPORTED_SYMPTOM_SOURCE")
            symptoms = [symptom.name for symptom in output.symptoms if symptom.status == "present"]
            coding = standardize(symptoms, cfg)
            candidates = [] if education else [item.model_dump() for item in output.differentials[:int(cfg["top_n"])]]
            if any(re.search(r"\d+(?:\.\d+)?\s*%", item["label"]) or re.search(r"(?:概率|可能性)[^。；]{0,8}\d+(?:\.\d+)?\s*%", item["rationale"]) for item in candidates):
                raise ValueError("UNCALIBRATED_MODEL_PERCENTAGE")
            calibration = probabilities(context, candidates, cfg)
            for item, probability in zip(candidates, calibration["values"], strict=True):
                item["probability"] = probability
                item["requires_doctor"] = True
            templates = [{"id": template["id"], "label": template["label"], "questions": template["questions"]}
                         for template in cfg.get("templates", []) if any(word in " ".join(texts) for word in template["keywords"])]
            context.facts["chief_complaint"] = output.chief_complaint
            context.facts["standardized_symptoms"] = symptoms
            need_followup = intake.get("status") == "awaiting_information"
            content = "已整理主诉：" + output.chief_complaint
            if candidates:
                content += "\n待医师核验的鉴别方向（不是确诊）：" + "、".join(item["label"] for item in candidates)
            content += "\n" + calibration["note"]
            return AgentResult(agent=self.name, content=content, metadata={"red_flags": [], "need_followup": need_followup,
                "symptoms": symptoms, "symptom_states": [s.model_dump() for s in output.symptoms], "coding": coding, "differentials": candidates, "probability": calibration,
                "templates": templates, "diagnostic_opinions": [{"claim": item["label"] + "：" + item["rationale"], "citation_ids": []} for item in candidates],
                "requires_doctor": True, "llm": response_metadata(response), "status": "completed"})
        except Exception as exc:
            return failure_result(self.name, exc)
