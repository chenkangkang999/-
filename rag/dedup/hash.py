"""内容 hash 去重：先规范化再 sha256，保证「同一段文字不同空白」只入一份。"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return _WHITESPACE.sub(" ", text).strip().lower()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
