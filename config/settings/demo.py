"""创空间单容器 CPU 演示配置（魔搭创空间等单容器部署场景）。

相比 base.py 只做四件事，其余全部继承：
1. WebSocket 通道层改用内存实现（无 Redis）
2. 前端 Vue3 构建产物由 whitenoise 直接托管（WHITENOISE_ROOT，不走 collectstatic，规避 manifest 哈希重写）
3. SPA history 路由 404 回退到 index.html
4. 放宽 ALLOWED_HOSTS（创空间经平台代理访问，Host 为平台域名）

数据库仍是 base.py 的默认 SQLite（未设 POSTGRES_HOST）；缓存/限流仍走 LocMem。
问诊执行走同步（CONSULTATION_EXECUTOR=sync，由 Dockerfile 环境变量设置）。
"""
from __future__ import annotations

import re

from django.http import HttpResponse

from .base import *  # noqa: F401,F403

# 1) 无 Redis：通道层内存化
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# 2) 前端静态托管（whitenoise 直接 serve，不走 collectstatic）
WHITENOISE_ROOT = BASE_DIR / "frontend" / "dist"

# 3) SPA fallback：Vue Router history 模式，非 API 路径 404 回退 index.html
_SPA_EXEMPT = re.compile(r"^/(api|admin|static|media|ws)/")


class SpaFallbackMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404 and not _SPA_EXEMPT.match(request.path):
            index = BASE_DIR / "frontend" / "dist" / "index.html"
            if index.exists():
                return HttpResponse(index.read_text(encoding="utf-8"), content_type="text/html")
        return response


MIDDLEWARE = list(MIDDLEWARE) + ["config.settings.demo.SpaFallbackMiddleware"]

# 4) 创空间经平台代理访问，放宽 Host 校验
ALLOWED_HOSTS = ["*"]

# 5) 允许被 iframe 嵌入（魔搭创空间用 iframe 展示应用页面）
#    base.py 的 XFrameOptionsMiddleware 会发 X-Frame-Options: DENY，
#    浏览器据此拦截 iframe 内容，页面显示"禁止访问"图标。
#    注意：本 Django 版本的该中间件不接受 X_FRAME_OPTIONS=None（会 .upper() 报错），
#    因此直接把它从 MIDDLEWARE 列表移除。
MIDDLEWARE = [
    m for m in MIDDLEWARE
    if m != "django.middleware.clickjacking.XFrameOptionsMiddleware"
]
