"""Stable integration contracts for the LLM and Web owners.

The four foundational agents and Coordinator keep their existing public API.
Private dependencies belong in ``context.facts['_llm']`` / ``['_emit']`` and
are never included in model prompts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    input_cached_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return asdict(self)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: LLMUsage
    model: str
    request_id: str | None = None


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str, *, agent: str) -> LLMResponse:
        """Return a provider response, preserving actual usage when available."""
        ...


class EventEmitter(Protocol):
    def __call__(self, agent: str, status: str, payload: dict[str, Any] | None = None) -> None:
        ...


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SOAP(StructuredOutput):
    subjective: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    assessment: str = Field(min_length=1)
    plan: str = Field(min_length=1)


class ExplanationOutput(StructuredOutput):
    soap: SOAP
    explanation: str = Field(min_length=1)
    care_guidance: list[str] = Field(min_length=1)
    citation_ids: list[str]


class SafetyReview(StructuredOutput):
    decision: Literal["pass", "replace", "block"]
    reasons: list[str]
    severity: Literal["low", "medium", "high", "critical"]
    regulation_ids: list[str]
    approved_text: str = ""


class DebatePosition(StructuredOutput):
    agent: str
    claim: str = Field(min_length=1)
    citation_ids: list[str]


class DebateConflict(StructuredOutput):
    topic: str = Field(min_length=1)
    positions: list[DebatePosition] = Field(min_length=2)


class ConflictDetection(StructuredOutput):
    conflicts: list[DebateConflict]
    summary: str = Field(min_length=1)


class DebateChallenge(StructuredOutput):
    challenges: list[str]
    evidence_gaps: list[str]


class DebateVerdict(StructuredOutput):
    conclusion: str = Field(min_length=1)
    rationale: list[str] = Field(min_length=1)
    unresolved: list[str]
    citation_ids: list[str]
    requires_doctor: bool
