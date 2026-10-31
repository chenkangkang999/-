"""统一异常出口：任何未捕获异常都返回可追踪的 error_id，不泄露堆栈。"""
from __future__ import annotations

import logging
import uuid

from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        error_id = uuid.uuid4().hex[:12]
        logger.exception("unhandled api error id=%s", error_id)
        return _build(500, "internal_error", "服务内部错误，请稍后重试", error_id)
    error_id = uuid.uuid4().hex[:12]
    response.data = {
        "error": {
            "code": getattr(exc, "default_code", "error"),
            "message": _flatten(response.data),
            "error_id": error_id,
        }
    }
    return response


def _flatten(data) -> str:
    if isinstance(data, dict):
        for value in data.values():
            return _flatten(value)
    if isinstance(data, list) and data:
        return _flatten(data[0])
    return str(data)


def _build(status: int, code: str, message: str, error_id: str):
    from rest_framework.response import Response

    return Response({"error": {"code": code, "message": message, "error_id": error_id}},
                    status=status)
