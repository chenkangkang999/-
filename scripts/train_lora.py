# -*- coding: utf-8 -*-
"""BGE-M3 LoRA 微调脚本。

- 基于 cMedQA2 三元组做对比学习（MultipleNegativesRankingLoss）
- sentence-transformers + PEFT LoRA，参数高效微调
- 所有配置从 scripts/training.yaml 读取，脚本不硬编码任何路径/超参

用法：
    python scripts/train_lora.py                          # 按默认配置训练
    python scripts/train_lora.py --max_train_samples 1000 # 覆盖训练样本上限
    python scripts/train_lora.py --no-train               # 自检：加载模型并打印可训练参数
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_triplets(path: Path, limit: int) -> list[dict]:
    """读取 {query, positive, negative} 三元组，返回样本列表。"""
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


def build_pairs_dataset(samples: list[dict]):
    """构造 anchor/positive 数据集（MultipleNegativesRankingLoss 用 in-batch negatives）。"""
    from datasets import Dataset

    return Dataset.from_list(
        [{"anchor": s["query"], "positive": s["positive"]} for s in samples]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="BGE-M3 LoRA 微调")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "scripts" / "training.yaml"))
    parser.add_argument("--max_train_samples", type=int, default=None, help="覆盖配置中的训练样本上限")
    parser.add_argument("--max_val_samples", type=int, default=None, help="覆盖配置中的验证样本上限")
    parser.add_argument("--no-train", action="store_true", help="仅加载模型并打印可训练参数（自检）")
    args = parser.parse_args()

    cfg = load_config(args.config)
    model_cfg, data_cfg = cfg["model"], cfg["data"]
    lora_cfg, train_cfg = cfg["lora"], cfg["train"]

    base_model_dir = resolve(model_cfg["local_dir"])
    output_dir = resolve(train_cfg["output_dir"])
    train_file = resolve(data_cfg["train_file"])
    val_file = resolve(data_cfg["val_file"])

    if not (base_model_dir / "config.json").exists():
        raise SystemExit(
            f"基座模型不存在：{base_model_dir}\n请先运行：python scripts/download_model.py"
        )

    import torch
    from peft import LoraConfig, TaskType
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.sentence_transformer.losses import MultipleNegativesRankingLoss
    from sentence_transformers.sentence_transformer.training_args import BatchSamplers

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[设备] {device} (cuda={torch.cuda.is_available()})")

    # 1. 加载基座模型
    model = SentenceTransformer(str(base_model_dir), device=device)
    model.max_seq_length = int(train_cfg.get("max_seq_length", 512))

    # 2. 挂载 LoRA adapter
    lora_kwargs: dict = {
        "task_type": TaskType.FEATURE_EXTRACTION,
        "inference_mode": False,
        "r": int(lora_cfg.get("r", 16)),
        "lora_alpha": int(lora_cfg.get("alpha", 32)),
        "lora_dropout": float(lora_cfg.get("dropout", 0.05)),
    }
    target = lora_cfg.get("target_modules")
    if target:  # 列表或字符串（如 "all-linear" 自动检测）
        lora_kwargs["target_modules"] = target
    model.add_adapter(LoraConfig(**lora_kwargs))

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"[LoRA] 可训练参数 {trainable:,} / 总参数 {total:,} ({trainable / total:.2%})")

    if args.no_train:
        print("[自检] 模型加载与 LoRA 挂载成功，未开始训练。")
        return

    # 3. 读取数据
    max_train = args.max_train_samples if args.max_train_samples is not None else int(data_cfg.get("max_train_samples", 0))
    max_val = args.max_val_samples if args.max_val_samples is not None else int(data_cfg.get("max_val_samples", 0))
    print("[数据] 读取训练集...")
    train_samples = load_triplets(train_file, max_train)
    val_samples = load_triplets(val_file, max_val)
    print(f"[数据] 训练 {len(train_samples)} 条, 验证 {len(val_samples)} 条（验证集仅供评测脚本使用）")
    train_dataset = build_pairs_dataset(train_samples)

    # 4. 对比学习 loss
    loss = MultipleNegativesRankingLoss(model)

    # 5. 训练参数
    training_args = SentenceTransformerTrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=float(train_cfg.get("num_epochs", 1)),
        per_device_train_batch_size=int(train_cfg.get("per_device_batch_size", 8)),
        gradient_accumulation_steps=int(train_cfg.get("gradient_accumulation_steps", 1)),
        learning_rate=float(train_cfg.get("learning_rate", 2e-4)),
        warmup_ratio=float(train_cfg.get("warmup_ratio", 0.1)),
        bf16=bool(train_cfg.get("bf16", False)),
        fp16=bool(train_cfg.get("fp16", False)),
        eval_strategy="no",
        save_strategy="steps",
        save_steps=int(train_cfg.get("save_steps", 1000)),
        save_total_limit=int(train_cfg.get("save_total_limit", 2)),
        batch_sampler=BatchSamplers.NO_DUPLICATES,
        logging_steps=int(train_cfg.get("logging_steps", 50)),
        seed=int(train_cfg.get("seed", 42)),
        report_to=[],
    )

    # 6. 训练
    trainer = SentenceTransformerTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        loss=loss,
    )
    trainer.train()

    # 7. 保存 adapter（PEFT 会保存 adapter_config.json + adapter_model.safetensors）
    final_dir = output_dir / "final"
    model.save_pretrained(str(final_dir))
    print(f"[完成] LoRA adapter 已保存到 {final_dir}")


if __name__ == "__main__":
    main()
