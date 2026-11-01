"""Persistent full-corpus BM25 using SQLite FTS5; no model or GPU dependency."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    result = re.findall(r"[a-z0-9_]+", normalized)
    for sequence in re.findall(r"[\u3400-\u9fff]+", normalized):
        result.extend(sequence)
        result.extend(sequence[i:i + 2] for i in range(len(sequence) - 1))
    return result


class SQLiteBM25:
    def __init__(self, path: str | Path, *, create: bool = False, timeout: float = 10):
        path = Path(path)
        if not create and not path.is_file():
            raise FileNotFoundError("BM25_INDEX_MISSING")
        self.connection = sqlite3.connect(str(path), timeout=timeout)
        if create:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    content_hash TEXT PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(chunk_id UNINDEXED, tokens);
            """)

    def add(self, chunk_id: str, text: str, content_hash: str) -> bool:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO items(content_hash, chunk_id) VALUES(?, ?)",
            (content_hash, chunk_id),
        )
        if cursor.rowcount:
            self.connection.execute("INSERT INTO passages(chunk_id,tokens) VALUES(?,?)", (chunk_id, " ".join(tokens(text))))
        return bool(cursor.rowcount)

    def commit(self):
        self.connection.commit()

    def search(self, query: str, limit: int, *, max_tokens: int = 64) -> list[tuple[str, float]]:
        terms = list(dict.fromkeys(tokens(query)))[:max_tokens]
        if not terms:
            return []
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        rows = self.connection.execute(
            "SELECT chunk_id, bm25(passages) FROM passages WHERE passages MATCH ? ORDER BY bm25(passages) LIMIT ?",
            (expression, limit),
        )
        return [(str(chunk_id), -float(score)) for chunk_id, score in rows]

    def close(self):
        self.connection.close()


def reciprocal_rank_fusion(rankings, *, weights, constant: int, limit: int):
    scores = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, (chunk_id, _) in enumerate(ranking, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (constant + rank)
    return sorted(scores.items(), key=lambda row: (-row[1], row[0]))[:limit]
