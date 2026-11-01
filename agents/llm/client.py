"""OpenAI-compatible HTTP adapter with accounting-safe retry behavior.

Only explicit HTTP 429 rejections may be retried. Timeouts, connection failures,
server failures and malformed responses have uncertain provider cost and are
surfaced immediately so the accounting wrapper can retain its reservation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from agents.contracts import LLMResponse, LLMUsage

PROTECTED_REQUEST_FIELDS = frozenset({
    "model", "messages", "stream", "stream_options", "max_tokens", "max_completion_tokens",
    "max_output_tokens", "temperature", "n",
})


class LLMConfigurationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LLMProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class OpenAICompatibleClient:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    timeout: float = 60.0
    max_retries: int = 2
    temperature: float = 0.2
    max_tokens: int = 2048
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    provider: str = "openai"
    request_options: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.request_options = _validated_request_options(self.request_options)

    @classmethod
    def from_env(cls) -> OpenAICompatibleClient:
        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
        model = os.getenv("LLM_MODEL", "").strip()
        if not api_key or not base_url or not model:
            raise LLMConfigurationError("LLM_NOT_CONFIGURED")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
            raise LLMConfigurationError("LLM_INVALID_BASE_URL")
        try:
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
            retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
            max_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))
            request_options = json.loads(os.getenv("LLM_REQUEST_OPTIONS", "{}"))
        except (TypeError, ValueError) as exc:
            raise LLMConfigurationError("LLM_INVALID_CONFIGURATION") from exc
        if timeout <= 0 or retries < 0 or not 0 <= temperature <= 2 or max_tokens <= 0:
            raise LLMConfigurationError("LLM_INVALID_CONFIGURATION")
        return cls(api_key, base_url, model, timeout, retries, temperature, max_tokens,
                   provider=os.getenv("LLM_PROVIDER", "openai"), request_options=request_options)

    def complete(self, system_prompt: str, user_prompt: str, *, agent: str) -> LLMResponse:
        del agent  # Accounting is supplied by the Web owner's injected wrapper.
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
            **_validated_request_options(self.request_options),
        }
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                except httpx.TimeoutException as exc:
                    # Retrying an ambiguous request could charge twice. Surface it.
                    raise LLMProviderError("TIMEOUT") from exc
                except httpx.RequestError as exc:
                    raise LLMProviderError("LLM_CONNECTION_ERROR") from exc
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        continue
                    raise LLMProviderError("RATE_LIMITED")
                if response.status_code >= 500:
                    raise LLMProviderError("LLM_PROVIDER_UNAVAILABLE")
                if not response.is_success:
                    # Never expose provider bodies/keys to AgentResult or logs.
                    raise LLMProviderError(f"LLM_HTTP_{response.status_code}")
                try:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("empty completion")
                    raw_usage = data.get("usage") or {}
                    usage = LLMUsage(
                        input_tokens=_token_count(raw_usage.get("prompt_tokens")),
                        output_tokens=_token_count(raw_usage.get("completion_tokens")),
                        total_tokens=_token_count(raw_usage.get("total_tokens")),
                        input_cached_tokens=_token_count(raw_usage.get("prompt_cache_hit_tokens",
                            (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens"))),
                    )
                    return LLMResponse(content, usage, data.get("model") or self.model,
                                       data.get("id"))
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise LLMProviderError("INVALID_PROVIDER_RESPONSE") from exc
        raise LLMProviderError("LLM_PROVIDER_UNAVAILABLE")


def _token_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid provider token count")
    return value


def _validated_request_options(options: object) -> dict[str, Any]:
    if not isinstance(options, dict) or any(not isinstance(key, str) for key in options):
        raise LLMConfigurationError("LLM_INVALID_CONFIGURATION")
    if PROTECTED_REQUEST_FIELDS.intersection(options):
        raise LLMConfigurationError("LLM_INVALID_CONFIGURATION")
    try:
        # Copy the JSON value, reject non-JSON objects and non-finite numbers.
        return json.loads(json.dumps(options, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as exc:
        raise LLMConfigurationError("LLM_INVALID_CONFIGURATION") from exc
