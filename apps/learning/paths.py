from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError


def digest(value):
    data = (
        value
        if isinstance(value, bytes)
        else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    )
    return hashlib.sha256(data).hexdigest()


def redact(value):
    text = str(value or "")
    for pattern in (
        r"(?<!\d)1[3-9]\d{9}(?!\d)",
        r"(?<!\w)[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r"(?<!\d)\d{17}[\dXx](?!\w)",
    ):
        text = re.sub(pattern, "[已脱敏]", text)
    return text


def bounded_path(path, roots):
    candidate = Path(path).resolve()
    if not any(candidate.is_relative_to(Path(root).resolve()) for root in roots):
        raise ValidationError({"code": "PATH_NOT_ALLOWED", "detail": "文件超出配置允许的目录"})
    return candidate


def read_json(path, roots):
    path = bounded_path(path, roots)
    if path.stat().st_size > settings.LEARNING_MAX_IMPORT_BYTES:
        raise ValidationError({"code": "ARTIFACT_TOO_LARGE", "detail": "训练产物超过导入大小限制"})
    return json.loads(path.read_text(encoding="utf-8-sig"))
