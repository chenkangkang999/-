"""测试配置：内存数据库 + 同步 Celery + 快速哈希，保证 CI 稳定。"""

from __future__ import annotations

from config.settings.base import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CONSULTATION_EXECUTOR = "inline"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# 测试环境不需要静态文件中间件（避免 staticfiles 目录告警）
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405
CLINICAL_INTAKE_ENABLED = False
TOKEN_BUCKET_ENABLED = False
TOKEN_BUCKET_BACKEND = "memory"
APPROVED_RESPONSE_CACHE_ENABLED = False
