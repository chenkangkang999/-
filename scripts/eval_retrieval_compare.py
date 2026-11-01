# -*- coding: utf-8 -*-
"""BGE-M3 三组检索评测对比（基座 vs 线性基线 vs 余弦调优）。

在 cMedQA2 验证集上，对三个模型各跑一遍 Recall@K / MRR / NDCG@K，
输出三组对比表（控制台 + CSV）。

复用 eval_retrieval 的 evaluate / load_triplets / build_candidates，
避免逻辑重复。模型路径均从 training.yaml 读取，不硬编码。

用法：
    python scripts/eval_retrieval_compare.py
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval_retrieval import (  # noqa: E402
    build_candidates,
    evaluate,
    load_config,
    load_triplets,
    resolve,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="BGE-M3 三组检索评测对比")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "scripts" / "training.yaml"))
    parser.add_argument("--max_val_samples", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    model_cfg, data_cfg = cfg["model"], cfg["data"]
    eval_cfg = cfg["eval"]

    base_model_dir = resolve(model_cfg["local_dir"])
    val_file = resolve(data_cfg["val_file"])

    # 三组待评测模型：{名称: adapter 目录（None = 基座不挂 adapter）}
    models = {
        "base": ("基座(微调前)", None),
        "baseline": ("线性基线", resolve("models/finetuned/bge-m3-lora-baseline")),
        "cosine": ("余弦调优", resolve("models/finetuned/bge-m3-lora") / "final"),
    }

    max_val = args.max_val_samples if args.max_val_samples is not None else int(data_cfg.get("max_val_samples", 1000))
    num_negatives = int(eval_cfg.get("num_negatives", 19))
    top_ks = [int(k) for k in eval_cfg.get("top_ks", [1, 5, 10])]
    seed = int(cfg["train"].get("seed", 42))
    out_csv = resolve("models/finetuned/eval_comparison_3way.csv")

    if not (base_model_dir / "config.json").exists():
        raise SystemExit(f"基座模型不存在：{base_model_dir}\n请先运行：python scripts/download_model.py")

    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[设备] {device}")

    val_samples = load_triplets(val_file, max_val)
    pools = build_candidates(val_samples, num_negatives, seed)
    print(f"[评测] 验证 {len(pools)} 条 query，每条候选 {1 + num_negatives} 个\n")

    # 逐个模型加载 + 评测
    metrics: dict[str, dict] = {}
    for key, (label, adapter_dir) in models.items():
        print(f"[评测] 加载 {label} ...")
        if adapter_dir is None:
            model = SentenceTransformer(str(base_model_dir), device=device)
        else:
            if not adapter_dir.exists():
                raise SystemExit(f"adapter 不存在：{adapter_dir}")
            model = SentenceTransformer(str(base_model_dir), device=device)
            model.load_adapter(str(adapter_dir))
        print(f"[评测] 计算 {label} 指标...")
        metrics[key] = evaluate(model, pools, top_ks)
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # 汇总表
    metric_names = [f"Recall@{k}" for k in top_ks] + ["MRR"] + [f"NDCG@{k}" for k in top_ks]
    print("\n" + "=" * 76)
    print("三组检索指标对比（cMedQA2 验证集）")
    print("=" * 76)
    header = f"{'指标':<12}{'基座':<14}{'线性基线':<14}{'余弦调优':<14}"
    print(header)
    print("-" * 76)

    rows = []
    for m in metric_names:
        b = metrics["base"][m]
        bl = metrics["baseline"][m]
        cs = metrics["cosine"][m]
        rows.append({"metric": m, "base": b, "baseline": bl, "cosine": cs,
                     "baseline_delta": bl - b, "cosine_delta": cs - b})
        print(f"{m:<12}{b:<14.4f}{bl:<14.4f}{cs:<14.4f}")

    # 提升幅度小结
    print("\n" + "-" * 76)
    print("相对基座提升：")
    for m in metric_names:
        bl_d = metrics["baseline"][m] - metrics["base"][m]
        cs_d = metrics["cosine"][m] - metrics["base"][m]
        print(f"  {m:<10} 线性基线 {bl_d:+.4f}   余弦调优 {cs_d:+.4f}")
    print("=" * 76)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "base", "baseline", "cosine",
                                                "baseline_delta", "cosine_delta"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[完成] 三组对比表已保存到 {out_csv}")


if __name__ == "__main__":
    main()
