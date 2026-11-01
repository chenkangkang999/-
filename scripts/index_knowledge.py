"""Explicit full-corpus index command; never starts on a page read."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")


def main():
    parser = argparse.ArgumentParser(description="对显式公共知识语料建全量或限量索引")
    parser.add_argument("--limit", type=int, default=None, help="0表示全量；非0为限量，不会标成全量完成")
    args = parser.parse_args()
    import django
    django.setup()
    from apps.rag.services.indexing import run_index
    run = run_index(limit=args.limit)
    print(json.dumps({"id": run.pk, "status": run.status, "documents": run.document_count,
                      "chunks": run.chunk_count, "deduplicated": run.skipped_duplicated, "stats": run.stats}, ensure_ascii=False))
    if run.status != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
