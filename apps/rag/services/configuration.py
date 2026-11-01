from __future__ import annotations

import hashlib
from pathlib import Path

from django.conf import settings

from rag.model_backends import RAGUnavailable, local_model_fingerprint


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else settings.BASE_DIR / path


def adapter_state():
    from apps.learning.models import ModelVersion
    from apps.learning.registry import active_adapter, adapter_fingerprint

    selected = ModelVersion.objects.filter(is_active=True).first()
    if selected:
        path = active_adapter()
        return path, selected.sha256
    if settings.RAG_ADAPTER_PATH:
        path, fingerprint = adapter_fingerprint(project_path(settings.RAG_ADAPTER_PATH))
        return str(path), fingerprint
    if settings.RAG_REQUIRE_ADAPTER:
        raise RAGUnavailable("ADAPTER_NOT_CONFIGURED")
    return None, "base"


def embedding_state():
    if not settings.RAG_ENABLE_MODEL_LOAD:
        raise RAGUnavailable("MODEL_LOADING_DISABLED")
    directory = project_path(settings.RAG_BASE_MODEL_PATH)
    base = local_model_fingerprint(directory)
    adapter, fingerprint = adapter_state()
    return directory, adapter, hashlib.sha256(f"{base}:{fingerprint}".encode()).hexdigest()
