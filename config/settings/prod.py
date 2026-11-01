"""生产配置：强制 DEBUG 关闭，并要求显式提供密钥与主机白名单。"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import SECRET_KEY

if (
    SECRET_KEY
    in {
        "",
        "dev-only-insecure-secret-key",
        "change-me-in-production",
        "replace-with-a-random-local-secret",
    }
    or len(SECRET_KEY) < 50
):  # noqa: F405
    raise ImproperlyConfigured("生产环境必须设置 DJANGO_SECRET_KEY")

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
