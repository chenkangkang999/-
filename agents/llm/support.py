"""Prompt loading, structured-output validation and public upstream snapshots."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from agents.base.agent import AgentResult
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.contracts import LLMResponse
from agents.llm import get_llm_client

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def prompt_path(name: str) -> Path:
    configured = os.getenv("LLM_PROMPTS_DIR", "").strip()
    return (Path(configured) if configured else PROMPTS_DIR) / f"{name}.md"


def load_prompt(name: str) -> str:
    text = prompt_path(name).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("EMPTY_SYSTEM_PROMPT")
    return text


def emit_started(context: AgentContext, agent: str) -> None:
    emitter = context.facts.get("_emit")
    if callable(emitter):
        try:
            emitter(agent, "started", None)
        except Exception:  # noqa: BLE001 - telemetry may not change medical decisions
            logger.warning("agent start telemetry failed: %s", agent)


def public_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): public_data(item) for key, item in value.items()
                if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [public_data(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def latest_steps(context: AgentContext) -> dict[str, dict[str, Any]]:
    return {step["agent"]: step for step in context.steps if "agent" in step}


def upstream_payload(context: AgentContext, message: AgentMessage,
                     *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    steps = latest_steps(context)
    return {
        "question": message.content,
        "patient": public_data(context.patient),
        "history": public_data(context.facts.get("history", [])),
        "upstream": [
            {"agent": name, "content": step.get("content", ""),
             "metadata": public_data(step.get("metadata", {})),
             "citations": public_data(step.get("citations", [])),
             "available": not bool(step.get("error"))}
            for name, step in steps.items() if name not in exclude
        ],
    }


def evidence(context: AgentContext) -> list[dict[str, Any]]:
    retrieval = latest_steps(context).get("retrieval", {})
    if retrieval.get("error"):
        return []
    citations = retrieval.get("citations") or []
    return [public_data(item) for item in citations if isinstance(item, dict)
            and isinstance(item.get("chunk_id"), str) and item["chunk_id"]]


def validate_citation_ids(ids: list[str], citations: list[dict[str, Any]]) -> None:
    allowed = {item["chunk_id"] for item in citations}
    if not set(ids).issubset(allowed):
        raise ValueError("UNKNOWN_CITATION_ID")


def complete_json[OutputT: BaseModel](context: AgentContext, agent: str, prompt: str,
                  payload: dict[str, Any], schema: type[OutputT]) -> tuple[OutputT, LLMResponse]:
    client = context.facts.get("_llm") or get_llm_client()
    system_prompt = load_prompt(prompt) + "\n\nJSON Schema:\n" + json.dumps(
        schema.model_json_schema(), ensure_ascii=False
    )
    response = client.complete(system_prompt, json.dumps(public_data(payload), ensure_ascii=False),
                               agent=agent)
    if not isinstance(response, LLMResponse):
        raise TypeError("INVALID_LLM_RESPONSE_CONTRACT")
    raw = response.content.strip()
    # Accept a single fenced JSON document; never scrape a fragment from prose.
    if raw.startswith("```json\n") and raw.endswith("```"):
        raw = raw[8:-3].strip()
    return schema.model_validate_json(raw), response


def response_metadata(response: LLMResponse) -> dict[str, Any]:
    return {"model": response.model, "request_id": response.request_id,
            "usage": response.usage.to_dict()}


def sanitized_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code and all(char.isupper() or char.isdigit() or char == "_"
                                             for char in code) and len(code) <= 64:
        return code
    if isinstance(exc, FileNotFoundError):
        return "PROMPT_CONFIGURATION_REQUIRED"
    if isinstance(exc, (ValidationError, ValueError, TypeError)):
        return "INVALID_OUTPUT"
    if isinstance(exc, ImportError) or str(exc).startswith("DEBATE_DEPENDENCY_UNAVAILABLE"):
        return "DEPENDENCY_UNAVAILABLE"
    return "AGENT_EXECUTION_FAILED"


def failure_result(agent: str, exc: Exception) -> AgentResult:
    code = sanitized_error_code(exc)
    # A ValidationError may contain the full model output; do not log the exception.
    logger.warning("agent failed: %s code=%s", agent, code)
    return AgentResult(agent=agent, content="", error=code,
                       metadata={"status": "failed", "error_code": code})
