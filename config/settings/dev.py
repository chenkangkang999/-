"""本地开发配置：默认 SQLite + 宽松的 CORS。"""
from __future__ import annotations

from config.settings.base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
