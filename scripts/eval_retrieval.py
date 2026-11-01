# -*- coding: utf-8 -*-
"""BGE-M3 微调前后检索评测对比。

对比「基座模型」与「LoRA 微调后」在 cMedQA2 验证集上的检索指标：
Recall@K / MRR / NDCG@K，输出对比表（控制台 + CSV）。

评测方式：每个 query 用 1 个 positive + N 个负例（来自其他样本的正答案）构造候选池，
看模型能否把 positive 排到前面。复用 rag.evaluation.metrics 的指标函数。

用法：
    python scripts/eval_retrieval.py
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.evaluation.metrics import recall_at_k, mrr, ndcg_at_k  # noqa: E402


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_triplets(path: Path, limit: int) -> list[dict]:
    samples: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("query") and obj.get("positive"):
                samples.append(obj)
            if limit and len(samples) >= limit:
                break
    return samples


def build_candidates(samples: list[dict], num_negatives: int, seed: int) -> list[tuple[str, list[str]]]:
    """每个 query 构造候选池：位置 0 为 positive，其后为 N 个负例（可复现）。"""
    rng = random.Random(seed)
    n = len(samples)
    positives = [s["positive"] for s in samples]
    queries = [s["query"] for s in samples]
    pools: list[tuple[str, list[str]]] = []
    for i in range(n):
        others = [j for j in range(n) if j != i]
        neg_idx = rng.sample(others, min(num_negatives, len(others)))
        cands = [positives[i]] + [positives[j] for j in neg_idx]
        pools.append((queries[i], cands))
    return pools


def evaluate(model, pools: list[tuple[str, list[str]]], top_ks: list[int]) -> dict:
    """返回 {metric_name: value}。"""
    import numpy as np

    recall_sums = {k: 0.0 for k in top_ks}
    ndcg_sums = {k: 0.0 for k in top_ks}
    mrr_sum = 0.0
    n = len(pools)

    for query, cands in pools:
        texts = [query] + cands
        embs = np.asarray(model.encode(texts, normalize_embeddings=True))
        q = embs[0]
        c = embs[1:]
        sims = (q @ c.T).tolist()
        order = sorted(range(len(cands)), key=lambda j: sims[j], reverse=True)
        ranked = [str(j) for j in order]
        relevant = ["0"]  # positive 始终在候选位置 0

        for k in top_ks:
            recall_sums[k] += recall_at_k(ranked, relevant, k)
            ndcg_sums[k] += ndcg_at_k(ranked, relevant, k)
        mrr_sum += mrr(ranked, relevant)

    result: dict = {}
    for k in top_ks:
        result[f"Recall@{k}"] = recall_sums[k] / n
    result["MRR"] = mrr_sum / n
    for k in top_ks:
        result[f"NDCG@{k}"] = ndcg_sums[k] / n
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BGE-M3 微调前后检索评测")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "scripts" / "training.yaml"))
    parser.add_argument("--max_val_samples", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    model_cfg, data_cfg = cfg["model"], cfg["data"]
    train_cfg, eval_cfg = cfg["train"], cfg["eval"]

    base_model_dir = resolve(model_cfg["local_dir"])
    adapter_dir = resolve(train_cfg["output_dir"]) / "final"
    val_file = resolve(data_cfg["val_file"])
    out_csv = resolve(eval_cfg["output_csv"])

    max_val = args.max_val_samples if args.max_val_samples is not None else int(data_cfg.get("max_val_samples", 1000))
    num_negatives = int(eval_cfg.get("num_negatives", 19))
    top_ks = [int(k) for k in eval_cfg.get("top_ks", [1, 5, 10])]
    seed = int(train_cfg.get("seed", 42))

    if not (base_model_dir / "config.json").exists():
        raise SystemExit(f"基座模型不存在：{base_model_dir}\n请先运行：python scripts/download_model.py")
    if not adapter_dir.exists():
        raise SystemExit(f"LoRA adapter 不存在：{adapter_dir}\n请先运行：python scripts/train_lora.py")

    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[设备] {device}")

    # 验证集
    val_samples = load_triplets(val_file, max_val)
    pools = build_candidates(val_samples, num_negatives, seed)
    print(f"[评测] 验证 {len(pools)} 条 query，每条候选 {1 + num_negatives} 个")

    # 基座（微调前）
    print("[评测] 加载基座模型...")
    base = SentenceTransformer(str(base_model_dir), device=device)

    # LoRA（微调后）
    print("[评测] 加载 LoRA 微调模型...")
    lora = SentenceTransformer(str(base_model_dir), device=device)
    lora.load_adapter(str(adapter_dir))

    print("[评测] 计算基座指标...")
    base_metrics = evaluate(base, pools, top_ks)
    print("[评测] 计算 LoRA 指标...")
    lora_metrics = evaluate(lora, pools, top_ks)

    # 汇总
    metric_names = [f"Recall@{k}" for k in top_ks] + ["MRR"] + [f"NDCG@{k}" for k in top_ks]
    print("\n" + "=" * 60)
    print("微调前后检索指标对比（cMedQA2 验证集）")
    print("=" * 60)
    print(f"{'指标':<12}{'基座(微调前)':<16}{'LoRA(微调后)':<16}{'提升':<10}")
    print("-" * 60)
    rows = []
    for m in metric_names:
        b, l = base_metrics[m], lora_metrics[m]
        delta = l - b
        rows.append({"metric": m, "base": b, "lora": l, "delta": delta})
        print(f"{m:<12}{b:<16.4f}{l:<16.4f}{delta:<+10.4f}")
    print("=" * 60)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "base", "lora", "delta"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[完成] 对比表已保存到 {out_csv}")


if __name__ == "__main__":
    main()
