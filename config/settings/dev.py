"""本地开发配置：默认 SQLite + 宽松的 CORS。"""

from __future__ import annotations

from config.settings.base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Explicit local, single-process mode; services mode uses Redis/Celery settings from base.
if os.getenv("APP_RUNTIME", "local") == "local":  # noqa: F405
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CONSULTATION_EXECUTOR = os.getenv("CONSULTATION_EXECUTOR", "thread")  # noqa: F405
