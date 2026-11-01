# -*- coding: utf-8 -*-
"""下载 BGE-M3 基座模型。

镜像源按 scripts/training.yaml 的 model.mirror 切换：
  - modelscope   阿里达摩院镜像（默认，国内快）
  - hf-mirror    HuggingFace 第三方镜像
  - huggingface  HuggingFace 官方

用法：
    python scripts/download_model.py
    python scripts/download_model.py --config path/to/training.yaml
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


def download_modelscope(model_id: str, local_dir: Path) -> str:
    from modelscope import snapshot_download

    return snapshot_download(model_id, local_dir=str(local_dir))


def download_huggingface(model_id: str, local_dir: Path, endpoint: str | None = None) -> str:
    from huggingface_hub import snapshot_download

    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint
    return snapshot_download(repo_id=model_id, local_dir=str(local_dir))


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 BGE-M3 基座模型")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "scripts" / "training.yaml"),
        help="配置文件路径",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    model_cfg = cfg["model"]
    model_id = model_cfg["model_id"]
    mirror = model_cfg.get("mirror", "modelscope")
    local_dir = resolve(model_cfg["local_dir"])
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"[下载] model={model_id}")
    print(f"[下载] mirror={mirror}")
    print(f"[下载] 目标目录={local_dir}")

    if mirror == "modelscope":
        download_modelscope(model_id, local_dir)
    elif mirror == "hf-mirror":
        download_huggingface(model_id, local_dir, endpoint="https://hf-mirror.com")
    else:
        download_huggingface(model_id, local_dir)

    files = sorted(p.name for p in local_dir.iterdir())
    print(f"[完成] 本地文件: {files}")

    required = ["config.json", "tokenizer.json", "sentencepiece.bpe.model"]
    missing = [f for f in required if not (local_dir / f).exists()]
    # 权重可能是单个 safetensors 或分片
    has_weight = any((local_dir / f).exists() for f in ("model.safetensors", "pytorch_model.bin")) or any(
        p.name.startswith("model-") and p.name.endswith(".safetensors") for p in local_dir.iterdir()
    )
    if not has_weight:
        missing.append("model.safetensors (或分片)")

    if missing:
        print(f"[警告] 缺少关键文件，下载可能不完整: {missing}")
    else:
        print("[OK] 关键文件齐全，可开始训练。")


if __name__ == "__main__":
    main()
