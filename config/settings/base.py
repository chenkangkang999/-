"""所有环境共享的 Django 配置。

约定：
- 密钥/连接串一律来自环境变量（.env 不入库）；
- 业务开关集中在文件末尾，便于答辩演示时逐项开关。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "channels",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.consultations",
    "apps.agents",
    "apps.rag",
    "apps.billing",
    "apps.monitoring",
    "apps.learning",
]

INSTALLED_APPS = ["daphne"] + DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# 数据库：默认 SQLite；配置了 POSTGRES_HOST 就走 PostgreSQL
# ---------------------------------------------------------------------------
if os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "medconsult"),
            "USER": os.getenv("POSTGRES_USER", "medconsult"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# 国际化
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF / CORS
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# ---------------------------------------------------------------------------
# Channels / Redis / Celery
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CACHE_IO_TIMEOUT = float(os.getenv("CACHE_IO_TIMEOUT", "5"))
CACHES = {"default": (
    {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL,
     "OPTIONS": {"socket_connect_timeout": CACHE_IO_TIMEOUT, "socket_timeout": CACHE_IO_TIMEOUT}}
    if os.getenv("APP_RUNTIME", "local") == "services"
    else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "medical-explicit-local"}
)}
SESSION_ENGINE = os.getenv("SESSION_ENGINE", "django.contrib.sessions.backends.cached_db" if os.getenv("APP_RUNTIME", "local") == "services" else "django.contrib.sessions.backends.db")
SESSION_CACHE_ALIAS = os.getenv("SESSION_CACHE_ALIAS", "default")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_DEFAULT_QUEUE = os.getenv("CELERY_TASK_DEFAULT_QUEUE", "default")

# ---------------------------------------------------------------------------
# 业务域配置（集中在一处，方便测试覆盖）
# ---------------------------------------------------------------------------
MILVUS_URI = os.getenv("MILVUS_URI", "http://127.0.0.1:19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "med_knowledge")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

ENABLE_DEBATE = env_bool("ENABLE_DEBATE", True)
ENABLE_SAFETY_GATE = env_bool("ENABLE_SAFETY_GATE", True)
DAILY_TOKEN_BUDGET_PER_USER = int(os.getenv("DAILY_TOKEN_BUDGET_PER_USER", "200000"))
DAILY_COST_BUDGET_PER_USER = os.getenv("DAILY_COST_BUDGET_PER_USER", "")
BILLING_CURRENCY = os.getenv("BILLING_CURRENCY", "CNY")
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))
BILLING_INPUT_TOKEN_OVERHEAD = int(os.getenv("BILLING_INPUT_TOKEN_OVERHEAD", "128"))
BILLING_ESTIMATOR_ENCODING = os.getenv("BILLING_ESTIMATOR_ENCODING", "cl100k_base")
COORDINATOR_PROVIDER = os.getenv("COORDINATOR_PROVIDER", "agents.base.coordinator.Coordinator")
HISTORY_PROVIDER = os.getenv(
    "HISTORY_PROVIDER", "apps.consultations.services.langchain_history.LangChainHistory"
)
HISTORY_MESSAGE_LIMIT = int(os.getenv("HISTORY_MESSAGE_LIMIT", "30"))
CLINICAL_INTAKE_ENABLED = env_bool("CLINICAL_INTAKE_ENABLED", True)
CLINICAL_INTAKE_EXTRACTOR = os.getenv("CLINICAL_INTAKE_EXTRACTOR", "llm")
CONSULTATION_EXECUTOR = os.getenv("CONSULTATION_EXECUTOR", "celery")
CONSULTATION_WORKERS = int(os.getenv("CONSULTATION_WORKERS", "2"))
ANSWER_CHUNK_SIZE = int(os.getenv("ANSWER_CHUNK_SIZE", "96"))
TOKEN_BUCKET_ENABLED = env_bool("TOKEN_BUCKET_ENABLED", True)
TOKEN_BUCKET_BACKEND = os.getenv("TOKEN_BUCKET_BACKEND", "memory" if os.getenv("APP_RUNTIME") == "local" else "redis")
TOKEN_BUCKET_CAPACITY = int(os.getenv("TOKEN_BUCKET_CAPACITY", "30"))
TOKEN_BUCKET_REFILL_PER_SECOND = float(os.getenv("TOKEN_BUCKET_REFILL_PER_SECOND", "0.5"))
TOKEN_BUCKET_MAX_KEYS = int(os.getenv("TOKEN_BUCKET_MAX_KEYS", "10000"))
APPROVED_RESPONSE_CACHE_ENABLED = env_bool("APPROVED_RESPONSE_CACHE_ENABLED", True)
APPROVED_RESPONSE_CACHE_TTL = int(os.getenv("APPROVED_RESPONSE_CACHE_TTL", "300"))
APPROVED_RESPONSE_CACHE_MAX_CHARS = int(os.getenv("APPROVED_RESPONSE_CACHE_MAX_CHARS", "40000"))
LEARNING_MANIFEST_PATH = Path(os.getenv("LEARNING_MANIFEST_PATH", str(BASE_DIR / "configs/learning_manifest.yaml")))
LEARNING_CONFIG_PATH = Path(os.getenv("LEARNING_CONFIG_PATH", str(BASE_DIR / "scripts/training.yaml")))
LEARNING_DATA_ROOT = Path(os.getenv("LEARNING_DATA_ROOT", str(BASE_DIR / "data")))
LEARNING_ARTIFACT_ROOT = Path(os.getenv("LEARNING_ARTIFACT_ROOT", str(BASE_DIR / "models/finetuned")))
LEARNING_HANDOFF_ROOT = Path(os.getenv("LEARNING_HANDOFF_ROOT", str(BASE_DIR / ".local/learning")))
LEARNING_MAX_IMPORT_BYTES = int(os.getenv("LEARNING_MAX_IMPORT_BYTES", "16777216"))
LEARNING_MAX_IMPORT_FILES = int(os.getenv("LEARNING_MAX_IMPORT_FILES", "200"))
LEARNING_MAX_DATASET_BYTES = int(os.getenv("LEARNING_MAX_DATASET_BYTES", "1073741824"))
LEARNING_MAX_CANDIDATES = int(os.getenv("LEARNING_MAX_CANDIDATES", "5000"))
LEARNING_STALE_SECONDS = int(os.getenv("LEARNING_STALE_SECONDS", "600"))
LEARNING_PREVIEW_RATE = os.getenv("LEARNING_PREVIEW_RATE", "30/min")
LEARNING_PREVIEW_MAX_ROWS = int(os.getenv("LEARNING_PREVIEW_MAX_ROWS", "5"))
LEARNING_PREVIEW_LINE_BYTES = int(os.getenv("LEARNING_PREVIEW_LINE_BYTES", "65536"))
LEARNING_PREVIEW_FIELD_CHARS = int(os.getenv("LEARNING_PREVIEW_FIELD_CHARS", "500"))
if not 1 <= LEARNING_PREVIEW_MAX_ROWS <= 10 or min(LEARNING_PREVIEW_LINE_BYTES, LEARNING_PREVIEW_FIELD_CHARS) <= 0:
    raise ValueError("训练样例最多允许1至10条，读取与字段长度限制必须为正数")
LEARNING_VALIDATION_PERCENT = int(os.getenv("LEARNING_VALIDATION_PERCENT", "10"))
LEARNING_REQUIRE_HOLDOUT = env_bool("LEARNING_REQUIRE_HOLDOUT", True)
LEARNING_PYTHON_EXECUTABLE = os.getenv("LEARNING_PYTHON_EXECUTABLE", "python")
if not 0 < LEARNING_VALIDATION_PERCENT < 100 or min(LEARNING_MAX_IMPORT_BYTES, LEARNING_MAX_IMPORT_FILES, LEARNING_MAX_DATASET_BYTES, LEARNING_MAX_CANDIDATES, LEARNING_STALE_SECONDS) <= 0:
    raise ValueError("训练导入限制必须为正数，验证集比例必须在0与100之间")
if min(HISTORY_MESSAGE_LIMIT, CONSULTATION_WORKERS, ANSWER_CHUNK_SIZE) <= 0:
    raise ValueError("历史条数、工作线程数和回复分块大小必须为正数")

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "agents": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# RAG: explicit full-corpus indexing; bm25 is a labeled CPU fallback.
RAG_MODE = os.getenv("RAG_MODE", "bm25")
RAG_CORPORA_MANIFEST = os.getenv("RAG_CORPORA_MANIFEST", "configs/rag_corpora.json")
RAG_ALLOWED_CORPUS_ROOTS = env_list("RAG_ALLOWED_CORPUS_ROOTS", str(BASE_DIR / "data"))
RAG_INDEX_DIR = os.getenv("RAG_INDEX_DIR", str(BASE_DIR / ".local/rag"))
RAG_MAX_MANIFEST_BYTES = int(os.getenv("RAG_MAX_MANIFEST_BYTES", "1048576"))
RAG_MAX_CORPUS_BYTES = int(os.getenv("RAG_MAX_CORPUS_BYTES", "1073741824"))
RAG_MAX_RECORD_CHARS = int(os.getenv("RAG_MAX_RECORD_CHARS", "200000"))
RAG_MAX_DOCUMENTS = int(os.getenv("RAG_MAX_DOCUMENTS", "0"))
RAG_INDEX_BATCH_SIZE = int(os.getenv("RAG_INDEX_BATCH_SIZE", "500"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_MAX_TOP_K = int(os.getenv("RAG_MAX_TOP_K", "20"))
RAG_RETRIEVAL_LIMIT = int(os.getenv("RAG_RETRIEVAL_LIMIT", "40"))
RAG_SNIPPET_CHARS = int(os.getenv("RAG_SNIPPET_CHARS", "500"))
RAG_QUERY_MAX_CHARS = int(os.getenv("RAG_QUERY_MAX_CHARS", "4000"))
RAG_QUERY_MAX_TOKENS = int(os.getenv("RAG_QUERY_MAX_TOKENS", "64"))
RAG_TIMEOUT_SECONDS = float(os.getenv("RAG_TIMEOUT_SECONDS", "15"))
RAG_DENSE_WEIGHT = float(os.getenv("RAG_DENSE_WEIGHT", "0.5"))
RAG_RRF_CONSTANT = int(os.getenv("RAG_RRF_CONSTANT", "60"))
RAG_MILVUS_URI = os.getenv("RAG_MILVUS_URI", MILVUS_URI)
RAG_MILVUS_TOKEN = os.getenv("RAG_MILVUS_TOKEN", "")
RAG_COLLECTION_PREFIX = os.getenv("RAG_COLLECTION_PREFIX", "medical_full")
RAG_ENABLE_MODEL_LOAD = env_bool("RAG_ENABLE_MODEL_LOAD", False)
RAG_BASE_MODEL_PATH = os.getenv("RAG_BASE_MODEL_PATH", "models/pretrained/BAAI/bge-m3")
RAG_ADAPTER_PATH = os.getenv("RAG_ADAPTER_PATH", "")
RAG_REQUIRE_ADAPTER = env_bool("RAG_REQUIRE_ADAPTER", True)
RAG_DEVICE = os.getenv("RAG_DEVICE", "cpu")
RAG_EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", "16"))
RAG_RERANKER = os.getenv("RAG_RERANKER", "none")
RAG_RERANK_MODEL_PATH = os.getenv("RAG_RERANK_MODEL_PATH", "models/reranker")
RAG_CACHE_ALIAS = os.getenv("RAG_CACHE_ALIAS", "default")
RAG_CACHE_TTL = int(os.getenv("RAG_CACHE_TTL", "300"))
if RAG_MODE not in {"bm25", "milvus"} or RAG_RERANKER not in {"none", "cross_encoder"}:
    raise ValueError("RAG模式或重排配置无效")
if not 0 <= RAG_CHUNK_OVERLAP < RAG_CHUNK_SIZE or not 0 <= RAG_DENSE_WEIGHT <= 1:
    raise ValueError("RAG切片重叠或融合权重无效")
if min(RAG_INDEX_BATCH_SIZE, RAG_MAX_TOP_K, RAG_RETRIEVAL_LIMIT, RAG_RRF_CONSTANT, RAG_TIMEOUT_SECONDS, RAG_CACHE_TTL, RAG_EMBED_BATCH_SIZE, CACHE_IO_TIMEOUT) <= 0 or RAG_MAX_DOCUMENTS < 0:
    raise ValueError("RAG数量与超时必须为正，文档上限0表示全量")
