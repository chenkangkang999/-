"""Versioned real retrieval. BM25 is explicit degradation, never fake BGE."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from django.conf import settings
from django.core.cache import caches

from apps.rag.models import Chunk, IndexRun
from apps.rag.services.configuration import embedding_state, project_path
from rag.dedup.hash import normalize_text
from rag.local_bm25 import SQLiteBM25, reciprocal_rank_fusion
from rag.model_backends import LocalBGE, LocalCrossEncoder, MilvusDense, RAGUnavailable

logger = logging.getLogger(__name__)
_model_lock = threading.RLock()


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source: str
    title: str
    snippet: str
    score: float
    url: str = ""
    source_hash: str = ""
    chunk_hash: str = ""
    corpus_kind: str = "unknown"
    authority: str = "web"
    index_version: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class SearchOutcome:
    results: list[RetrievedChunk] = field(default_factory=list)
    status: str = "not_connected"
    mode: str = ""
    degraded: bool = False
    error_code: str = ""
    index_version: str = ""
    model_version: str = ""
    rerank_status: str = "not_configured"
    cache_status: str = "miss"
    latency_ms: float = 0

    def metadata(self):
        value = asdict(self)
        value.pop("results")
        value["hits"] = len(self.results)
        return value


@lru_cache(maxsize=2)
def _encoder(directory, adapter, version, device, batch_size):
    return LocalBGE(directory, adapter, device=device, batch_size=batch_size)


@lru_cache(maxsize=2)
def _reranker(directory, device):
    return LocalCrossEncoder(directory, device=device)


def _run_search(query, top_k):
    mode = settings.RAG_MODE
    result = SearchOutcome(mode=mode, degraded=mode == "bm25")
    latest = IndexRun.objects.filter(status="succeeded", stats__mode=mode).order_by("-finished_at", "-pk").first()
    if latest is None:
        result.error_code = "INDEX_NOT_READY"
        return result
    result.index_version = str(latest.pk)
    directory = adapter = None
    result.model_version = latest.stats["model_version"]
    if mode == "milvus":
        directory, adapter, current_version = embedding_state()
        if current_version != result.model_version:
            raise RAGUnavailable("MODEL_INDEX_VERSION_MISMATCH")
    rerank = settings.RAG_RERANKER
    if rerank not in {"none", "cross_encoder"}:
        raise RAGUnavailable("INVALID_RERANKER")
    if rerank == "cross_encoder" and not settings.RAG_ENABLE_MODEL_LOAD:
        raise RAGUnavailable("MODEL_LOADING_DISABLED")
    reranker_path = project_path(settings.RAG_RERANK_MODEL_PATH)
    reranker_version = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in reranker_path.glob("*") if p.is_file()] if rerank != "none" else []
    key_payload = [mode, latest.pk, result.model_version, rerank, reranker_version, settings.RAG_DENSE_WEIGHT, settings.RAG_RRF_CONSTANT, settings.RAG_RETRIEVAL_LIMIT, top_k, normalize_text(query)]
    key = "rag:v2:" + hashlib.sha256(json.dumps(key_payload, sort_keys=True).encode()).hexdigest()
    cache = caches[settings.RAG_CACHE_ALIAS]
    try:
        cached = cache.get(key)
    except Exception:
        cached = None
        result.cache_status = "unavailable"
    if cached is not None:
        result.results = [RetrievedChunk(**row) for row in cached]
        result.status = "hits" if cached else "no_hits"
        result.rerank_status = "applied" if rerank != "none" else "not_configured"
        result.cache_status = "hit"
        return result
    index = SQLiteBM25(latest.stats["index_path"], timeout=settings.RAG_TIMEOUT_SECONDS)
    try:
        sparse = index.search(query, settings.RAG_RETRIEVAL_LIMIT, max_tokens=settings.RAG_QUERY_MAX_TOKENS)
    finally:
        index.close()
    ranking = sparse
    if mode == "milvus":
        with _model_lock:
            encoder = _encoder(str(directory), adapter, result.model_version, settings.RAG_DEVICE, settings.RAG_EMBED_BATCH_SIZE)
            vector = encoder.encode([query])[0]
        dense = MilvusDense(settings.RAG_MILVUS_URI, settings.RAG_MILVUS_TOKEN, timeout=settings.RAG_TIMEOUT_SECONDS, collection=latest.stats["collection"])
        try:
            dense_hits = dense.search(vector, settings.RAG_RETRIEVAL_LIMIT)
        finally:
            dense.close()
        ranking = reciprocal_rank_fusion([dense_hits, sparse], weights=[settings.RAG_DENSE_WEIGHT, 1 - settings.RAG_DENSE_WEIGHT], constant=settings.RAG_RRF_CONSTANT, limit=settings.RAG_RETRIEVAL_LIMIT)
    ids = [row[0] for row in ranking]
    chunks = {str(row.pk): row for row in Chunk.objects.select_related("document").filter(pk__in=ids)}
    if rerank == "cross_encoder" and ranking:
        with _model_lock:
            model = _reranker(str(reranker_path), settings.RAG_DEVICE)
            ranking = model.rank(query, [(pk, chunks[pk].text) for pk in ids if pk in chunks])
        result.rerank_status = "applied"
    for pk, score in ranking[:top_k]:
        if pk not in chunks:
            continue
        chunk = chunks[pk]
        document = chunk.document
        result.results.append(RetrievedChunk(chunk_id=pk, source=document.source, title=document.title, snippet=chunk.text[:settings.RAG_SNIPPET_CHARS], score=score, url=document.url, source_hash=document.content_hash, chunk_hash=chunk.metadata.get("content_hash", ""), corpus_kind=document.metadata.get("corpus_kind", "unknown"), authority=document.authority, index_version=result.index_version))
    result.status = "hits" if result.results else "no_hits"
    try:
        cache.set(key, [row.to_dict() for row in result.results], timeout=settings.RAG_CACHE_TTL)
    except Exception:
        result.cache_status = "unavailable"
    return result


def search_with_status(query, top_k=None, *, user=None, trace_id="", run_id=""):
    started = time.perf_counter()
    query = str(query or "").strip()
    if not query or len(query) > settings.RAG_QUERY_MAX_CHARS:
        return SearchOutcome(status="invalid_query", error_code="INVALID_QUERY", mode=settings.RAG_MODE)
    limit = settings.RAG_TOP_K if top_k is None else int(top_k)
    if not 1 <= limit <= settings.RAG_MAX_TOP_K:
        return SearchOutcome(status="invalid_query", error_code="INVALID_TOP_K", mode=settings.RAG_MODE)
    try:
        result = _run_search(query, limit)
    except RAGUnavailable as exc:
        result = SearchOutcome(status="not_connected", error_code=exc.code, mode=settings.RAG_MODE, degraded=settings.RAG_MODE == "bm25")
    except Exception as exc:
        timed_out = isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower() or "timeout" in str(getattr(exc, "message", "")).lower()
        result = SearchOutcome(status="error", error_code="RETRIEVAL_TIMEOUT" if timed_out else "RETRIEVAL_FAILED", mode=settings.RAG_MODE)
        logger.warning("Retrieval failed type=%s", type(exc).__name__)
    result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    from apps.monitoring.services import record_failure, record_metric

    if result.status in {"hits", "no_hits"}:
        labels = {"mode": result.mode, "index_version": result.index_version, "cache": result.cache_status}
        record_metric("retrieval.latency_ms", result.latency_ms, user=user, trace_id=trace_id, labels=labels)
        record_metric("retrieval.hit_count", len(result.results), user=user, trace_id=trace_id, labels=labels)
    elif result.status == "error":
        record_failure(result.error_code, source="retrieval", user=user, trace_id=trace_id, run_id=run_id)
    else:
        record_metric("retrieval.unavailable", 1, user=user, trace_id=trace_id, labels={"code": result.error_code})
    return result


def search_chunks(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Compatibility API; callers needing status should use search_with_status."""
    return search_with_status(query, top_k).results
