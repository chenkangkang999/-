from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register
from agents.contracts import SafetyReview
from agents.llm.support import (
    complete_json,
    emit_started,
    latest_steps,
    response_metadata,
    sanitized_error_code,
    upstream_payload,
)

logger = logging.getLogger(__name__)
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "prompts" / "safety_rules.json"


class CandidateUnavailableError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LocalRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    pattern: str
    reason: str
    severity: Literal["low", "medium", "high", "critical"]
    regulation_ids: list[str]
    negation_pattern: str | None = None


class SafetyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    urgent_levels: list[str]
    messages: dict[str, str]
    regulations: dict[str, dict[str, Any]]
    contraindication_regulation_ids: list[str]
    rules: list[LocalRule] = Field(min_length=1)


def load_policy() -> SafetyPolicy:
    configured = os.getenv("SAFETY_RULES_PATH", "").strip()
    path = Path(configured) if configured else DEFAULT_RULES_PATH
    policy = SafetyPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    for required in ("disclaimer", "blocked", "emergency", "contraindication"):
        if not policy.messages.get(required, "").strip():
            raise ValueError("INVALID_SAFETY_MESSAGES")
    for rule in policy.rules:
        re.compile(rule.pattern)
        if rule.negation_pattern:
            re.compile(rule.negation_pattern)
        if not set(rule.regulation_ids).issubset(policy.regulations):
            raise ValueError("UNKNOWN_RULE_REGULATION")
    if not set(policy.contraindication_regulation_ids).issubset(policy.regulations):
        raise ValueError("UNKNOWN_RULE_REGULATION")
    return policy


def local_hits(text: str, policy: SafetyPolicy) -> list[LocalRule]:
    hits = []
    for rule in policy.rules:
        for match in re.finditer(rule.pattern, text, re.IGNORECASE):
            if rule.negation_pattern and re.search(rule.negation_pattern, match.group()):
                continue
            hits.append(rule)
            break
    return hits


def append_disclaimer(text: str, policy: SafetyPolicy) -> str:
    disclaimer = policy.messages["disclaimer"]
    return text if disclaimer in text else f"{text.rstrip()}\n\n{disclaimer}"


@register
class SafetyAgent(BaseAgent):
    name = "safety"
    description = "完整候选回复的本地规则与 LLM 双判、监管溯源与失败关闭"
    system_prompt = "agents/prompts/safety.md"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        emit_started(context, self.name)
        try:
            return self._review(context, message)
        except Exception as exc:  # noqa: BLE001 - never release an unreviewed candidate
            code = sanitized_error_code(exc)
            logger.warning("safety review failed: %s", code)
            return AgentResult(
                agent=self.name, content="", error=str(code),
                metadata={"decision": "block", "approved_text": "", "blocked": True,
                          "reasons": ["安全审核未完成，候选内容未发布。"],
                          "severity": "high", "regulations": [], "review_status": "failed",
                          "error_code": code},
            )

    def _review(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        policy = load_policy()
        steps = latest_steps(context)
        candidate = context.facts.get("candidate_text")
        if candidate is None:
            candidate = steps.get("explainer", {}).get("content", "")
        if not isinstance(candidate, str):
            raise ValueError("INVALID_CANDIDATE_ANSWER")
        candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        base = {"reviewed_candidate_sha256": candidate_hash, "policy_version": policy.version}
        risk = steps.get("risk", {}).get("metadata", {})
        red_flags = risk.get("red_flags") or context.facts.get("red_flags")
        if risk.get("risk_level") in policy.urgent_levels or red_flags:
            return self._result(
                policy, "replace", policy.messages["emergency"],
                ["上游已识别紧急风险，优先给出急诊指引。"], "critical", [],
                {**base, "escalate": True, "review_status": "emergency_rule"},
            )
        medication = steps.get("medication", {}).get("metadata", {})
        if medication.get("contraindications") or medication.get("blocked_drugs"):
            return self._result(
                policy, "replace", policy.messages["contraindication"],
                ["上游报告用药禁忌，需要医师或药师核验。"], "high",
                policy.contraindication_regulation_ids,
                {**base, "review_status": "contraindication_rule"},
            )
        if not candidate.strip():
            code = steps.get("explainer", {}).get("metadata", {}).get("error_code")
            raise CandidateUnavailableError(code or "UPSTREAM_UNAVAILABLE")
        hits = local_hits(candidate, policy)
        if hits:
            ids = list(dict.fromkeys(item for rule in hits for item in rule.regulation_ids))
            return self._result(
                policy, "block", policy.messages["blocked"], [rule.reason for rule in hits],
                "high", ids, {**base, "rule_ids": [rule.id for rule in hits],
                              "review_status": "rule_block"},
            )
        payload = upstream_payload(context, message, exclude=("safety",))
        payload.update({"candidate_text": candidate, "regulations": policy.regulations})
        review, response = complete_json(context, self.name, "safety", payload, SafetyReview)
        if not set(review.regulation_ids).issubset(policy.regulations):
            raise ValueError("UNKNOWN_REGULATION_ID")
        extra = {**base, "llm": response_metadata(response), "review_status": "dual_review"}
        if review.severity == "critical":
            return self._result(policy, "replace", policy.messages["emergency"], review.reasons,
                                "critical", review.regulation_ids, {**extra, "escalate": True})
        if review.decision == "block":
            return self._result(policy, "block", policy.messages["blocked"], review.reasons,
                                review.severity, review.regulation_ids, extra)
        if review.decision == "replace":
            replacement = review.approved_text.strip()
            if not replacement or local_hits(replacement, policy):
                raise ValueError("INVALID_SAFETY_REPLACEMENT")
            payload["candidate_text"] = replacement
            payload["replacement_review"] = True
            confirmation, second_response = complete_json(
                context, self.name, "safety", payload, SafetyReview
            )
            if confirmation.decision != "pass" or confirmation.severity == "critical":
                raise ValueError("SAFETY_REPLACEMENT_NOT_APPROVED")
            if not set(confirmation.regulation_ids).issubset(policy.regulations):
                raise ValueError("UNKNOWN_REGULATION_ID")
            extra["replacement_review_llm"] = response_metadata(second_response)
            return self._result(policy, "replace", replacement, review.reasons,
                                review.severity, review.regulation_ids, extra)
        return self._result(policy, "pass", candidate, review.reasons, review.severity,
                            review.regulation_ids, extra)

    def _result(self, policy: SafetyPolicy, decision: str, approved: str, reasons: list[str],
                severity: str, regulation_ids: list[str], extra: dict[str, Any]) -> AgentResult:
        approved = append_disclaimer(approved, policy)
        return AgentResult(
            agent=self.name, content=approved,
            metadata={"decision": decision, "approved_text": approved,
                      "blocked": decision != "pass", "reasons": reasons, "severity": severity,
                      "regulations": [policy.regulations[item] for item in regulation_ids],
                      **extra},
        )
