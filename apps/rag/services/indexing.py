"""Stream explicitly configured public corpora into a versioned full-corpus index."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from itertools import islice

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.rag.models import Chunk, Document, IndexRun
from apps.rag.services.configuration import embedding_state, project_path
from rag.dedup.hash import content_hash
from rag.indexing.chunker import chunk_text
from rag.local_bm25 import SQLiteBM25
from rag.model_backends import LocalBGE, MilvusDense, RAGUnavailable

ALLOWED_KINDS = {"community_qa", "clinical_guideline", "consensus", "paper", "textbook"}


def public_text(value):
    text = str(value or "")
    for pattern in (r"(?<!\d)1[3-9]\d{9}(?!\d)", r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", r"(?<!\d)\d{17}[\dXx](?!\w)"):
        text = re.sub(pattern, "[已脱敏]", text)
    return text


def corpus_manifest():
    path = project_path(settings.RAG_CORPORA_MANIFEST)
    if not path.is_file():
        raise RAGUnavailable("CORPUS_MANIFEST_MISSING")
    if path.stat().st_size > settings.RAG_MAX_MANIFEST_BYTES:
        raise RAGUnavailable("CORPUS_MANIFEST_TOO_LARGE")
    value = json.loads(path.read_text(encoding="utf-8"))
    entries = value.get("corpora", [])
    if not entries:
        raise RAGUnavailable("CORPUS_NOT_CONFIGURED")
    for entry in entries:
        if entry.get("kind") not in ALLOWED_KINDS or entry.get("public_corpus") is not True:
            raise RAGUnavailable("PUBLIC_CORPUS_CONFIRMATION_REQUIRED")
        path = project_path(entry["path"]).resolve()
        if not any(path.is_relative_to(project_path(root).resolve()) for root in settings.RAG_ALLOWED_CORPUS_ROOTS):
            raise RAGUnavailable("CORPUS_PATH_NOT_ALLOWED")
        if not path.is_file():
            raise RAGUnavailable("CORPUS_FILE_MISSING")
        if path.stat().st_size > settings.RAG_MAX_CORPUS_BYTES:
            raise RAGUnavailable("CORPUS_FILE_TOO_LARGE")
        if entry.get("format") not in {"jsonl", "csv", "text"} or not entry.get("source"):
            raise RAGUnavailable("INVALID_CORPUS_CONFIG")
        entry["resolved_path"] = path
    return entries


def records(entry):
    path = entry["resolved_path"]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        if entry["format"] == "csv":
            yield from csv.DictReader(handle)
        elif entry["format"] == "jsonl":
            for line in handle:
                if len(line) > settings.RAG_MAX_RECORD_CHARS:
                    raise RAGUnavailable("CORPUS_RECORD_TOO_LARGE")
                if line.strip():
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise RAGUnavailable("INVALID_CORPUS_RECORD")
                    yield value
        else:
            # A text corpus is one document, bounded before reading.
            if path.stat().st_size > settings.RAG_MAX_RECORD_CHARS:
                raise RAGUnavailable("CORPUS_RECORD_TOO_LARGE")
            yield {entry.get("text_field", "text"): handle.read()}


def run_index(*, limit=None):
    limit = settings.RAG_MAX_DOCUMENTS if limit is None else limit
    if limit < 0:
        raise ValueError("索引数量不能为负，0代表显式语料全量")
    run = IndexRun.objects.create(stats={"mode": settings.RAG_MODE, "processed_rows": 0, "limited": bool(limit)})
    root = project_path(settings.RAG_INDEX_DIR)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "index.lock"
    lock = None
    bm25 = dense = None
    try:
        try:
            lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RAGUnavailable("INDEX_ALREADY_RUNNING") from exc
        os.write(lock, str(run.pk).encode())
        entries = corpus_manifest()
        if settings.RAG_MODE not in {"bm25", "milvus"}:
            raise RAGUnavailable("INVALID_RAG_MODE")
        encoder = None
        model_version = "bm25-no-model"
        if settings.RAG_MODE == "milvus":
            directory, adapter, model_version = embedding_state()
            encoder = LocalBGE(directory, adapter, device=settings.RAG_DEVICE, batch_size=settings.RAG_EMBED_BATCH_SIZE)
            collection = f"{settings.RAG_COLLECTION_PREFIX}_{run.pk}_{model_version[:12]}"
            dense = MilvusDense(settings.RAG_MILVUS_URI, settings.RAG_MILVUS_TOKEN, timeout=settings.RAG_TIMEOUT_SECONDS, collection=collection, dimension=encoder.dimension, create=True)
            run.stats["collection"] = collection
        index_file = root / f"index-{run.pk}.sqlite3"
        bm25 = SQLiteBM25(index_file, create=True, timeout=settings.RAG_TIMEOUT_SECONDS)
        run.stats.update(index_path=str(index_file), model_version=model_version, corpus_kinds=list(dict.fromkeys(e["kind"] for e in entries)), source_files=[])
        seen_rows = 0
        seen_documents = set()
        for entry in entries:
            source_stat = entry["resolved_path"].stat()
            source_hasher = hashlib.sha256()
            with entry["resolved_path"].open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    source_hasher.update(block)
            file_sha = source_hasher.hexdigest()
            run.stats["source_files"].append({"source": entry["source"], "file_sha256": file_sha, "kind": entry["kind"]})
            iterator = iter(records(entry))
            while True:
                remaining = max(0, limit - seen_rows) if limit else settings.RAG_INDEX_BATCH_SIZE
                batch = list(islice(iterator, min(settings.RAG_INDEX_BATCH_SIZE, remaining)))
                if not batch:
                    break
                dense_rows, texts = [], []
                with transaction.atomic():
                    for value in batch:
                        text = public_text(value.get(entry.get("text_field", "text"), "")).strip()
                        title = public_text(value.get(entry.get("title_field", "title"), entry.get("title", entry["source"])))[:256]
                        if not text or len(text) > settings.RAG_MAX_RECORD_CHARS:
                            raise RAGUnavailable("INVALID_CORPUS_TEXT")
                        url = str(value.get(entry.get("url_field", "url"), entry.get("url", "")))
                        if url and not re.match(r"^https?://", url):
                            raise RAGUnavailable("INVALID_CORPUS_URL")
                        authority = "guideline" if entry["kind"] == "clinical_guideline" else (entry["kind"] if entry["kind"] in {"paper", "consensus", "textbook"} else "web")
                        document, created = Document.objects.get_or_create(content_hash=content_hash(text), defaults={"title": title, "source": entry["source"][:512], "url": url, "authority": authority, "metadata": {"corpus_kind": entry["kind"], "public_corpus": True, "source_file_sha256": file_sha, "source_row": seen_rows + 1}})
                        if document.pk in seen_documents:
                            run.skipped_duplicated += 1
                            run.stats["duplicate_document_rows"] = run.stats.get("duplicate_document_rows", 0) + 1
                            seen_rows += 1
                            continue
                        else:
                            seen_documents.add(document.pk)
                            run.document_count += 1
                            run.stats["reused_documents"] = run.stats.get("reused_documents", 0) + int(not created)
                        for seq, piece in enumerate(chunk_text(text, size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP)):
                            hashed = content_hash(piece)
                            chunk, _ = Chunk.objects.get_or_create(document=document, seq=seq, defaults={"text": piece, "metadata": {"content_hash": hashed, "corpus_kind": document.metadata.get("corpus_kind", entry["kind"])}})
                            if bm25.add(str(chunk.pk), piece, hashed):
                                texts.append(piece)
                                dense_rows.append({"id": str(chunk.pk)})
                                run.chunk_count += 1
                            else:
                                run.skipped_duplicated += 1
                                run.stats["duplicate_chunks"] = run.stats.get("duplicate_chunks", 0) + 1
                        seen_rows += 1
                if dense_rows:
                    vectors = encoder.encode(texts) if encoder else []
                    if dense:
                        dense.upsert([{**row, "vector": vector} for row, vector in zip(dense_rows, vectors, strict=True)])
                bm25.commit()
                run.stats["processed_rows"] = seen_rows
                run.save(update_fields=["document_count", "chunk_count", "skipped_duplicated", "stats"])
                if limit and seen_rows >= limit:
                    break
            current_stat = entry["resolved_path"].stat()
            if (source_stat.st_size, source_stat.st_mtime_ns) != (current_stat.st_size, current_stat.st_mtime_ns):
                raise RAGUnavailable("CORPUS_CHANGED_DURING_INDEX")
            if limit and seen_rows >= limit:
                break
        if not run.chunk_count:
            raise RAGUnavailable("CORPUS_EMPTY")
        run.stats["full_corpus"] = not bool(limit)
        run.status = IndexRun.Status.SUCCEEDED
    except Exception as exc:
        run.status = IndexRun.Status.FAILED
        run.stats["error_code"] = getattr(exc, "code", "INDEXING_FAILED")
    finally:
        if bm25:
            bm25.close()
        if dense:
            dense.close()
        if lock is not None:
            os.close(lock)
            lock_path.unlink(missing_ok=True)
        run.finished_at = timezone.now()
        run.save()
    return run
