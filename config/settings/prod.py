"""生产配置：强制 DEBUG 关闭，并要求显式提供密钥与主机白名单。"""
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *  # noqa: F401,F403

if SECRET_KEY == "dev-only-insecure-secret-key":  # noqa: F405
    raise ImproperlyConfigured("生产环境必须设置 DJANGO_SECRET_KEY")

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
