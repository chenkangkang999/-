from __future__ import annotations

import hashlib
import json

import pytest
from django.core.cache import cache

from apps.rag.models import Chunk, Document, IndexRun
from apps.rag.services.engine import search_with_status
from apps.rag.services.indexing import run_index
from rag.local_bm25 import SQLiteBM25, reciprocal_rank_fusion

pytestmark = pytest.mark.django_db


@pytest.fixture
def corpus(settings, tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    entries = [
        {"text": "咳嗽伴随咽痛，测试公共资料", "title": "测试一"},
        {"text": "咳嗽伴随咽痛，测试公共资料", "title": "重复"},
        {"text": "饮食和血压记录，测试公共资料", "title": "测试二"},
    ]
    (source / "test.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in entries), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "corpora": [
                    {
                        "path": str(source / "test.jsonl"),
                        "format": "jsonl",
                        "source": "synthetic-unit-corpus",
                        "kind": "community_qa",
                        "public_corpus": True,
                        "url": "https://example.test/corpus",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    settings.RAG_CORPORA_MANIFEST = str(manifest)
    settings.RAG_ALLOWED_CORPUS_ROOTS = [str(source)]
    settings.RAG_INDEX_DIR = str(tmp_path / "index")
    settings.RAG_MODE = "bm25"
    settings.RAG_RERANKER = "none"
    cache.clear()
    return manifest


def test_real_bm25_full_index_dedup_and_rebuild_are_truthful(corpus):
    first = run_index(limit=0)
    assert first.status == "succeeded"
    assert first.document_count == 2 and first.chunk_count == 2 and first.skipped_duplicated == 1
    assert first.stats["processed_rows"] == 3 and first.stats["full_corpus"] is True
    second = run_index(limit=0)
    assert second.document_count == 2 and second.chunk_count == 2
    assert Document.objects.count() == 2 and Chunk.objects.count() == 2
    assert second.stats["reused_documents"] == 2
    result = search_with_status("咳嗽")
    assert result.status == "hits" and result.degraded is True and result.mode == "bm25"
    assert result.results[0].source_hash and result.results[0].corpus_kind == "community_qa"
    assert search_with_status("咳嗽").cache_status == "hit"
    assert search_with_status("不存在的xyzunmatched").status == "no_hits"


def test_missing_index_is_not_a_no_hit(corpus):
    result = search_with_status("咳嗽")
    assert result.status == "not_connected" and result.error_code == "INDEX_NOT_READY"


def test_limit_and_untrusted_corpus_are_not_claimed_as_full(corpus):
    limited = run_index(limit=1)
    assert limited.status == "succeeded" and limited.stats["full_corpus"] is False
    value = json.loads(corpus.read_text())
    value["corpora"][0]["public_corpus"] = False
    corpus.write_text(json.dumps(value), encoding="utf-8")
    failed = run_index(limit=0)
    assert (
        failed.status == "failed"
        and failed.stats["error_code"] == "PUBLIC_CORPUS_CONFIRMATION_REQUIRED"
    )


def test_rag_status_permissions_and_invalid_top_k(auth_client, corpus):
    assert auth_client.get("/api/v1/rag/status/").status_code == 403
    assert auth_client.get("/api/v1/rag/search/?q=test&top_k=abc").status_code == 400
    assert auth_client.get("/api/v1/rag/search/?q=test&top_k=-1").status_code == 400


def test_chinese_bm25_and_rrf_use_actual_scores(tmp_path):
    index = SQLiteBM25(tmp_path / "s.sqlite3", create=True)
    assert index.add("1", "咳嗽与呼吸", hashlib.sha256(b"one").hexdigest())
    assert not index.add("2", "重复", hashlib.sha256(b"one").hexdigest())
    index.commit()
    assert index.search("咳嗽", 5)[0][0] == "1"
    index.close()
    fused = reciprocal_rank_fusion(
        [[("a", 10), ("b", 2)], [("b", 1), ("a", 0)]], weights=[0.7, 0.3], constant=60, limit=2
    )
    assert fused[0][0] == "a" and fused[0][1] > fused[1][1]


def test_milvus_model_gate_does_not_fall_back_as_if_connected(corpus, settings):
    settings.RAG_MODE = "milvus"
    settings.RAG_ENABLE_MODEL_LOAD = False
    failed = run_index(limit=0)
    assert failed.status == "failed" and failed.stats["error_code"] == "MODEL_LOADING_DISABLED"
    assert not IndexRun.objects.filter(status="succeeded").exists()
