"""Real, local-only model and Milvus adapters. Optional libraries import lazily."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


class RAGUnavailable(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def local_model_fingerprint(directory):
    directory = Path(directory)
    if not (directory / "config.json").is_file():
        raise RAGUnavailable("BASE_MODEL_MISSING")
    weights = sorted([*directory.glob("*.safetensors"), *directory.glob("pytorch_model*.bin")])
    if not weights:
        raise RAGUnavailable("BASE_MODEL_WEIGHTS_MISSING")
    payload = [hashlib.sha256((directory / "config.json").read_bytes()).hexdigest(),
               [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in weights]]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


class LocalBGE:
    def __init__(self, directory, adapter=None, *, device="cpu", batch_size=16):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RAGUnavailable("EMBEDDING_DEPENDENCIES_MISSING") from exc
        self.model = SentenceTransformer(str(directory), device=device, local_files_only=True, trust_remote_code=False)
        if adapter:
            self.model.load_adapter(str(adapter))
        self.batch_size = batch_size
        self.dimension = self.model.get_sentence_embedding_dimension()

    def encode(self, texts):
        values = self.model.encode(texts, normalize_embeddings=True, batch_size=self.batch_size, show_progress_bar=False)
        return values.tolist()


class LocalCrossEncoder:
    def __init__(self, directory, *, device="cpu"):
        if not (Path(directory) / "config.json").is_file():
            raise RAGUnavailable("RERANK_MODEL_MISSING")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RAGUnavailable("RERANK_DEPENDENCIES_MISSING") from exc
        self.model = CrossEncoder(str(directory), device=device, local_files_only=True, trust_remote_code=False)

    def rank(self, query, passages):
        scores = self.model.predict([(query, text) for _, text in passages]).tolist()
        if any(not isinstance(score, (float, int)) or not math.isfinite(score) for score in scores):
            raise RAGUnavailable("RERANK_INVALID_OUTPUT")
        return sorted([(row[0], float(score)) for row, score in zip(passages, scores, strict=True)], key=lambda row: row[1], reverse=True)


class MilvusDense:
    def __init__(self, uri, token, *, timeout, collection, dimension=None, create=False):
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RAGUnavailable("MILVUS_DEPENDENCIES_MISSING") from exc
        self.client = MilvusClient(uri=uri, token=token, timeout=timeout)
        self.collection, self.timeout = collection, timeout
        exists = self.client.has_collection(collection_name=collection, timeout=timeout)
        if create and not exists:
            self.client.create_collection(collection_name=collection, dimension=dimension, primary_field_name="id", id_type="string", max_length=64, vector_field_name="vector", metric_type="COSINE", timeout=timeout)
        elif not exists:
            raise RAGUnavailable("MILVUS_INDEX_MISSING")

    def upsert(self, rows):
        self.client.upsert(collection_name=self.collection, data=rows, timeout=self.timeout)

    def search(self, vector, limit):
        result = self.client.search(collection_name=self.collection, data=[vector], limit=limit, anns_field="vector", search_params={"metric_type": "COSINE"}, timeout=self.timeout)
        return [(str(hit["id"]), float(hit["distance"])) for hit in result[0]]

    def close(self):
        self.client.close()
