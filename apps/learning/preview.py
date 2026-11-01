from __future__ import annotations

import csv
import json

from django.conf import settings
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.throttling import UserRateThrottle

from apps.learning.paths import bounded_path, redact
from apps.learning.training import project_path


class DatasetChanged(APIException):
    status_code = 409
    default_detail = "数据文件已变化或尚未核验，请先同步数据资产再查看样例"
    default_code = "dataset_changed"


class PreviewLimit(APIException):
    status_code = 413
    default_detail = "样例记录超过读取大小限制，未返回部分内容"
    default_code = "preview_limit"


class PreviewThrottle(UserRateThrottle):
    scope = "learning_preview"

    def get_rate(self):
        return settings.LEARNING_PREVIEW_RATE


def preview(asset, raw_limit):
    try:
        limit = int(raw_limit)
    except (ValueError, TypeError):
        raise ValidationError("样例数量必须为整数") from None
    if not 1 <= limit <= settings.LEARNING_PREVIEW_MAX_ROWS:
        raise ValidationError(f"样例数量必须在1至{settings.LEARNING_PREVIEW_MAX_ROWS}之间")
    path = bounded_path(project_path(asset.path), [project_path(settings.LEARNING_DATA_ROOT)])
    if not path.is_file():
        raise NotFound("源数据文件缺失，请重新同步资产")
    initial = path.stat()
    if (
        asset.file_status != "verified"
        or initial.st_size != asset.bytes
        or initial.st_mtime_ns != asset.verified_mtime_ns
    ):
        raise DatasetChanged()
    if initial.st_size > settings.LEARNING_MAX_DATASET_BYTES:
        raise PreviewLimit()
    if asset.format not in {"jsonl", "csv"}:
        raise ValidationError("该文件格式不支持安全样例预览")
    rows, fields = [], []
    total_bytes = 0

    def bounded_lines(handle):
        nonlocal total_bytes
        while True:
            line = handle.readline(settings.LEARNING_PREVIEW_LINE_BYTES + 1)
            if not line:
                return
            total_bytes += len(line)
            if (
                len(line) > settings.LEARNING_PREVIEW_LINE_BYTES
                or total_bytes > settings.LEARNING_PREVIEW_LINE_BYTES * (limit + 2)
            ):
                raise PreviewLimit()
            yield line.decode("utf-8-sig")

    try:
        with path.open("rb") as handle:
            lines = bounded_lines(handle)
            records = (
                (json.loads(line) for line in lines if line.strip())
                if asset.format == "jsonl"
                else csv.DictReader(lines)
            )
            for value in records:
                if not isinstance(value, dict) or len(value) > 32:
                    raise ValidationError("样例必须是字段数不超过32的对象")
                row = {}
                for key, item in value.items():
                    name = redact(str(key))[:64]
                    text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                    row[name] = redact(text)[: settings.LEARNING_PREVIEW_FIELD_CHARS]
                    if name not in fields:
                        fields.append(name)
                rows.append(row)
                if len(rows) >= limit:
                    break
    except (ValueError, UnicodeDecodeError, csv.Error):
        raise ValidationError("源文件格式错误，未返回未验证的样例") from None
    final = path.stat()
    if final.st_size != initial.st_size or final.st_mtime_ns != initial.st_mtime_ns:
        raise DatasetChanged()
    return {
        "asset_key": asset.key,
        "fields": fields,
        "results": rows,
        "sampled_rows": len(rows),
        "note": "自动遮盖常见标识，仍需人工复核；仅展示有限样例，不代表全部数据质量。",
    }
