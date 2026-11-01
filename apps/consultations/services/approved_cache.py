"""Only cache published, approved education; raw LLM candidates never enter Redis."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache


def key_for(run, context):
    if not settings.APPROVED_RESPONSE_CACHE_ENABLED or context.facts.get("history") or run.metadata.get("intake_submission"):
        return None
    from apps.consultations.services.intake import policy
    rules = policy()
    if not re.search(rules["education_pattern"], run.message.content.strip()) or re.search(rules["personal_pattern"], run.message.content):
        return None
    from apps.learning.models import ModelVersion
    from apps.rag.models import IndexRun
    versions = []
    files = [*Path(settings.BASE_DIR / "agents/prompts").glob("*"), *Path(settings.BASE_DIR / "configs").glob("*")]
    if os.getenv("LLM_PROMPTS_DIR"):
        files.extend(Path(os.environ["LLM_PROMPTS_DIR"]).glob("*"))
    for custom in (os.getenv("SAFETY_RULES_PATH"), os.getenv("CLINICAL_INTAKE_POLICY_PATH")):
        if custom:
            files.append(Path(custom))
    for path in sorted(set(files)):
        if path.is_file() and path.suffix in {".json", ".yaml", ".md"}:
            versions.append([str(path), hashlib.sha256(path.read_bytes()).hexdigest()])
    model = [getattr(settings, name, "") for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_MAX_OUTPUT_TOKENS", "RAG_MODE")]
    latest = IndexRun.objects.filter(status="succeeded", stats__mode=settings.RAG_MODE).order_by("-finished_at", "-pk").first()
    embedding_version = None
    if settings.RAG_MODE == "milvus":
        from apps.rag.services.configuration import embedding_state
        try:
            embedding_version = embedding_state()[2]
        except Exception:
            return None
        if latest is None or latest.stats.get("model_version") != embedding_version:
            return None
    active = ModelVersion.objects.filter(is_active=True).values_list("sha256", flat=True).first()
    from apps.consultations.services.clinical_evidence import index_path
    from apps.consultations.services.clinical_evidence import policy as clinical_policy
    index = index_path(clinical_policy())
    clinical_version = [index.stat().st_size, index.stat().st_mtime_ns] if index.is_file() else None
    inputs = [run.consultation.user_id, run.message.content, context.patient, versions, model, latest.pk if latest else None, embedding_version, active, clinical_version]
    return "approved-education:v1:" + hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load(key):
    if not key:
        return None
    try:
        raw = cache.get(key)
        value = json.loads(raw) if isinstance(raw, str) else None
        if not value or value["audit"].get("decision") != "pass" or not isinstance(value["text"], str):
            return None
        if hashlib.sha256(value["text"].encode()).hexdigest() != value["text_sha256"]:
            return None
        from agents.specialists.safety import load_policy, local_hits
        if local_hits(value["text"], load_policy()):
            return None
        return value
    except Exception:
        return None  # Cache is optional; perform fresh, metered review on a miss.


def store(key, text, details, citations, audit):
    if not key or audit.get("decision") != "pass" or len(text) > settings.APPROVED_RESPONSE_CACHE_MAX_CHARS:
        return
    payload = {"text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
               "details": details, "citations": citations, "audit": audit}
    try:
        cache.set(key, json.dumps(payload, ensure_ascii=False), timeout=settings.APPROVED_RESPONSE_CACHE_TTL)
    except Exception:
        pass
