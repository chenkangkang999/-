"""健康检查：给容器探针与前端连通性检测共用。"""
from __future__ import annotations

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - 探针必须永远返回而不是抛
        db_ok = False
    return JsonResponse({"status": "ok" if db_ok else "degraded", "database": db_ok})
