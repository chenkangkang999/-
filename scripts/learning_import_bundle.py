"""Import an operator-supplied observation/data bundle without loading pickle/model code."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--historical-config")
    parser.add_argument("--confirmed-early-stop", action="store_true")
    args = parser.parse_args()
    if Path(args.run_name).name != args.run_name or args.run_name in {".", ".."}:
        raise ValueError("Invalid run name")
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()
    from django.conf import settings

    from apps.learning.paths import bounded_path
    from apps.learning.training import config, project_path, synchronize

    cfg = config()
    directory = project_path(settings.LEARNING_ARTIFACT_ROOT) / args.run_name
    data_targets = {
        Path(cfg["data"][key]).name: bounded_path(
            project_path(cfg["data"][key]), [project_path(settings.LEARNING_DATA_ROOT)]
        )
        for key in ("train_file", "val_file")
    }
    allowed = {
        "trainer_state.json",
        "training_run.json",
        "training_events.jsonl",
        "evaluation_manifest.json",
        "eval_comparison.csv",
        "eval_comparison_3way.csv",
        "adapter_config.json",
        "adapter_model.safetensors",
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
    provenance = {"archive_sha256": file_hash(Path(args.archive)), "extracted": [], "skipped": []}
    with zipfile.ZipFile(args.archive) as archive:
        infos = archive.infolist()
        if (
            len(infos) > settings.LEARNING_MAX_IMPORT_FILES
            or sum(item.file_size for item in infos) > settings.LEARNING_MAX_DATASET_BYTES
        ):
            raise ValueError("Bundle exceeds configured limits")
        for info in infos:
            source = PurePosixPath(info.filename.replace("\\", "/"))
            if (
                source.is_absolute()
                or ".." in source.parts
                or any(":" in part for part in source.parts)
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise ValueError("Unsafe archive entry")
            if info.is_dir():
                continue
            if source.name in data_targets:
                target = data_targets[source.name]
            elif source.name in allowed:
                parts = source.parts[1:] if len(source.parts) > 1 else source.parts
                target = bounded_path(directory.joinpath(*parts), [directory])
            else:
                provenance["skipped"].append(source.name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".importing")
            incoming = hashlib.sha256()
            with archive.open(info) as handle, temporary.open("xb") as output:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    incoming.update(chunk)
                    output.write(chunk)
            if target.exists():
                if file_hash(target) != incoming.hexdigest():
                    temporary.unlink()
                    raise FileExistsError(f"Different existing content: {target.name}")
            else:
                # Creating a hard link is atomic and refuses to replace an existing file.
                os.link(temporary, target)
            temporary.unlink()
            provenance["extracted"].append(
                {"name": str(source), "sha256": incoming.hexdigest(), "bytes": info.file_size}
            )
    if args.confirmed_early_stop:
        if not args.historical_config:
            raise ValueError("Historical training configuration must be supplied explicitly")
        snapshot = yaml.safe_load(Path(args.historical_config).read_text(encoding="utf-8"))
        marker = {
            "label": args.run_name,
            "status": "early_stopped",
            "phase": "evaluation",
            "config": snapshot,
            "provenance": {
                "kind": "user_confirmed_historical",
                "zip_sha256": provenance["archive_sha256"],
                "stop_reason": "用户明确确认该轮在checkpoint终点触发早停；未重新执行训练",
                "note": "历史配置快照来自同学文档；checkpoint和CSV分别核验，未证明CSV模型指纹匹配，不自动启用。",
            },
        }
        marker_path = directory / "training_run.json"
        if marker_path.exists() and json.loads(marker_path.read_text(encoding="utf-8")) != marker:
            raise FileExistsError("A different run observation already exists")
        marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt = (
        project_path(settings.LEARNING_HANDOFF_ROOT)
        / "receipts"
        / f"{provenance['archive_sha256']}.json"
    )
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "archive_sha256": provenance["archive_sha256"],
                "extracted_files": len(provenance["extracted"]),
                "skipped_files": provenance["skipped"],
                "sync": synchronize(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
