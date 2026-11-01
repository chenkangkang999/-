from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import yaml
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from apps.learning.models import DatasetAsset, EvaluationReport, TrainingEvent, TrainingRun
from apps.learning.paths import bounded_path, digest, read_json, redact

METRIC_KEYS = {
    "loss",
    "eval_loss",
    "learning_rate",
    "grad_norm",
    "epoch",
    "train_loss",
    "train_runtime",
    "train_samples_per_second",
}
STATUSES = {"unknown", "running", "completed", "early_stopped", "failed", "interrupted", "ready"}


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else settings.BASE_DIR / path


def safe_config(value):
    if not isinstance(value, dict):
        raise ValidationError("训练配置必须是对象")
    # Never expose arbitrary configuration sections or credential-bearing mirror URLs.
    allowed = {
        "model": {"model_id", "mirror", "local_dir"},
        "lora": {"r", "alpha", "dropout", "target_modules"},
        "data": {
            "train_file",
            "val_file",
            "max_train_samples",
            "max_val_samples",
            "use_explicit_negatives",
        },
        "train": {
            "output_dir",
            "num_epochs",
            "per_device_batch_size",
            "gradient_accumulation_steps",
            "max_seq_length",
            "learning_rate",
            "warmup_ratio",
            "lr_scheduler_type",
            "weight_decay",
            "bf16",
            "fp16",
            "early_stopping",
            "early_stopping_patience",
            "eval_steps",
            "logging_steps",
            "seed",
        },
        "eval": {"num_negatives", "top_ks", "output_csv"},
    }
    return {
        section: {key: val for key, val in value.get(section, {}).items() if key in keys}
        for section, keys in allowed.items()
    }


def config():
    with project_path(settings.LEARNING_CONFIG_PATH).open(encoding="utf-8") as handle:
        return safe_config(yaml.safe_load(handle))


def load_manifest():
    """Read configuration only; page GETs must never initialize database rows."""
    with project_path(settings.LEARNING_MANIFEST_PATH).open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)
    if not isinstance(manifest, dict):
        raise ValidationError("数据资产清单必须是对象")
    return manifest


def ensure_manifest():
    """Materialize configuration only from explicit sync/import commands."""
    manifest = load_manifest()
    for item in manifest.get("datasets", []):
        DatasetAsset.objects.update_or_create(
            key=item["key"],
            defaults={
                key: item[key] for key in ("title", "source", "path", "format", "reported_rows")
            },
        )
    report = manifest.get("reported_evaluation")
    if report:
        EvaluationReport.objects.update_or_create(
            source_key="document_reported",
            defaults={
                "title": report["title"],
                "source": "document_reported",
                "verified": False,
                "scope": {**report["scope"], "provenance": manifest["source"]},
                "metrics": report["metrics"],
                "selected_model": report.get("selected_model", ""),
                "sha256": digest(report),
            },
        )
    return manifest


def dataset_payload(asset):
    return {
        key: getattr(asset, key)
        for key in (
            "id",
            "key",
            "title",
            "source",
            "path",
            "format",
            "reported_rows",
            "observed_rows",
            "file_status",
            "bytes",
            "sha256",
            "provenance",
            "checked_at",
        )
    }


def verify_dataset(asset):
    path = bounded_path(project_path(asset.path), [project_path(settings.LEARNING_DATA_ROOT)])
    asset.checked_at = timezone.now()
    if not path.is_file():
        asset.file_status, asset.observed_rows, asset.bytes, asset.sha256 = (
            "missing",
            None,
            None,
            "",
        )
        asset.provenance = "document_reported"
        asset.verified_mtime_ns = None
    elif path.stat().st_size > settings.LEARNING_MAX_DATASET_BYTES:
        asset.file_status = "error"
        asset.observed_rows = None
        asset.bytes = path.stat().st_size
    else:
        import hashlib

        initial = path.stat()
        fingerprint = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                fingerprint.update(chunk)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            if asset.format == "csv":
                rows = csv.reader(handle)
                next(rows, None)
                count = sum(bool(row) for row in rows)
            else:
                count = 0
                for line in handle:
                    if line.strip():
                        json.loads(line)
                        count += 1
        final = path.stat()
        if (initial.st_size, initial.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
            raise ValidationError("数据文件在核验时变化，请复制完成后重新同步")
        asset.file_status, asset.observed_rows, asset.bytes = "verified", count, final.st_size
        asset.sha256, asset.provenance = fingerprint.hexdigest(), "verified_file"
        asset.verified_mtime_ns = final.st_mtime_ns
    asset.save()


def metrics_only(value):
    return {
        key: val
        for key, val in value.items()
        if key in METRIC_KEYS
        and isinstance(val, (int, float))
        and not isinstance(val, bool)
        and math.isfinite(val)
    }


def add_event(run, value):
    # Only metrics and controlled operation messages; no trainer prompts/samples/console dump.
    metrics = metrics_only(value.get("metrics", value))
    kind = str(value.get("kind", "metric"))[:40]
    phase = str(value.get("phase", "training"))[:40]
    message = (
        redact(value.get("message", ""))[:2000]
        if kind
        in {"started", "completed", "failed", "interrupted", "prepared", "evaluation", "approved"}
        else ""
    )
    payload = {
        "kind": kind,
        "phase": phase,
        "message": message,
        "step": value.get("step"),
        "metrics": metrics,
    }
    TrainingEvent.objects.get_or_create(
        run=run,
        fingerprint=digest(payload),
        defaults={**payload, "level": "error" if kind == "failed" else "info"},
    )


def sync_run(directory, state_path=None):
    roots = [
        project_path(settings.LEARNING_ARTIFACT_ROOT),
        project_path(settings.LEARNING_HANDOFF_ROOT),
    ]
    directory = bounded_path(directory, roots)
    run_state = directory / "training_run.json"
    observed = read_json(run_state, roots) if run_state.exists() else {}
    state = read_json(state_path, roots) if state_path else {}
    if not isinstance(observed, dict) or not isinstance(state, dict):
        raise ValidationError("训练状态文件必须是对象")
    key = digest(str(directory))
    defaults = {
        "label": redact(observed.get("label", directory.name))[:160],
        "source": str(
            directory.relative_to(
                next(
                    Path(root).resolve()
                    for root in roots
                    if directory.is_relative_to(Path(root).resolve())
                )
            )
        ),
        "config": config(),
    }
    run, _ = TrainingRun.objects.get_or_create(source_key=key, defaults=defaults)
    if observed.get("run_id"):
        try:
            prepared = TrainingRun.objects.get(pk=observed["run_id"])
        except (TrainingRun.DoesNotExist, ValueError):
            pass
        else:
            if run.pk != prepared.pk and not run.events.exists():
                run.delete()
                prepared.source_key = key
                prepared.save(update_fields=["source_key"])
                run = prepared
    run.label, run.source = defaults["label"], defaults["source"]
    if isinstance(observed.get("config"), dict):
        run.config = safe_config(observed["config"])
    if isinstance(observed.get("provenance"), dict):
        run.provenance = {
            key: redact(str(value))[:2000]
            for key, value in observed["provenance"].items()
            if key in {"kind", "zip_sha256", "stop_reason", "note"}
        }
    run.artifact_path = str(directory)
    run.current_step = max(
        0, int(state.get("global_step", 0)), int(observed.get("current_step", 0))
    )
    max_steps = state.get("max_steps", observed.get("total_steps"))
    run.total_steps = int(max_steps) if max_steps is not None and int(max_steps) > 0 else None
    run.epoch = state.get("epoch")
    status = observed.get("status", "unknown")
    run.status = status if status in STATUSES else "unknown"
    if (
        run.status == "running"
        and run_state.exists()
        and timezone.now().timestamp() - run_state.stat().st_mtime > settings.LEARNING_STALE_SECONDS
    ):
        run.status = "unknown"
    # Standard trainer_state alone does not prove a live process or successful completion.
    run.phase = str(observed.get("phase", "training"))[:40]
    for key_name in ("started_at", "finished_at"):
        value = observed.get(key_name)
        if value:
            setattr(run, key_name, parse_datetime(value))
    history = state.get("log_history", [])
    if not isinstance(history, list):
        raise ValidationError("训练历史必须是数组")
    for item in history:
        if isinstance(item, dict):
            add_event(run, item)
    if history and isinstance(history[-1], dict):
        run.metrics = metrics_only(history[-1])
    if isinstance(state.get("best_metric"), (float, int)):
        run.metrics["best_eval_loss"] = state["best_metric"]
    event_file = directory / "training_events.jsonl"
    if event_file.exists():
        bounded_path(event_file, roots)
        if event_file.stat().st_size > settings.LEARNING_MAX_IMPORT_BYTES:
            raise ValidationError("训练事件文件超过导入限制")
        for line in event_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                add_event(run, json.loads(line))
    run.save()
    return run


def import_evaluation(path):
    roots = [
        project_path(settings.LEARNING_ARTIFACT_ROOT),
        project_path(settings.LEARNING_HANDOFF_ROOT),
    ]
    path = bounded_path(path, roots)
    if path.stat().st_size > settings.LEARNING_MAX_IMPORT_BYTES:
        raise ValidationError("评测文件超过导入限制")
    data = path.read_bytes()
    rows = []
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        if "metric" not in row:
            raise ValidationError("评测CSV缺少metric列")
        parsed = {"metric": row["metric"]}
        for key in ("base", "baseline", "cosine", "lora"):
            if row.get(key) not in (None, ""):
                value = float(row[key])
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValidationError("检索评测指标应在0至1之间")
                parsed["baseline" if key == "lora" else key] = value
        if len(parsed) > 1:
            rows.append(parsed)
    if not rows:
        raise ValidationError("评测CSV没有有效指标行")
    cfg = config()
    provenance_file = path.parent / "evaluation_manifest.json"
    evidence = read_json(provenance_file, roots) if provenance_file.exists() else {}
    if evidence and evidence.get("csv_sha256") != digest(data):
        raise ValidationError("评测CSV与运行清单指纹不一致")
    EvaluationReport.objects.update_or_create(
        source_key=digest(str(path)),
        defaults={
            "run": TrainingRun.objects.filter(source_key=digest(str(path.parent))).first(),
            "title": path.name,
            "source": "artifact",
            "verified": True,
            "metrics": rows,
            "sha256": digest(data),
            "selected_model": "baseline",
            "artifacts": {
                key: evidence[key] for key in ("adapter_sha256", "csv_sha256") if key in evidence
            },
            "scope": {
                "kind": "candidate_pool",
                "positive": 1,
                "negative": cfg["eval"].get("num_negatives"),
                "candidates": 1 + cfg["eval"].get("num_negatives", 0),
                "queries": evidence.get("queries"),
                "note": "从真实CSV导入；没有模型指纹清单时不证明与某checkpoint一一对应，非全库Recall",
            },
        },
    )


def synchronize():
    ensure_manifest()
    errors = []
    for asset in DatasetAsset.objects.all():
        try:
            verify_dataset(asset)
        except (OSError, ValueError, ValidationError):
            asset.file_status = "error"
            asset.observed_rows, asset.sha256, asset.provenance = None, "", "document_reported"
            asset.save(update_fields=["file_status", "observed_rows", "sha256", "provenance"])
            errors.append({"source": asset.key, "code": "DATASET_READ_FAILED"})
    groups, evaluations = {}, []
    files_seen = 0
    for root in (
        project_path(settings.LEARNING_ARTIFACT_ROOT),
        project_path(settings.LEARNING_HANDOFF_ROOT),
    ):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name not in {
                "trainer_state.json",
                "training_run.json",
                "eval_comparison.csv",
                "eval_comparison_3way.csv",
            }:
                continue
            files_seen += 1
            if files_seen > settings.LEARNING_MAX_IMPORT_FILES:
                errors.append({"code": "IMPORT_FILE_LIMIT"})
                break
            try:
                bounded_path(path, [root])
                if path.suffix == ".csv":
                    evaluations.append(path)
                    continue
                directory = (
                    path.parent.parent
                    if path.parent.name.startswith("checkpoint-")
                    else path.parent
                )
                group = groups.setdefault(directory, [])
                if path.name == "trainer_state.json":
                    group.append(path)
            except (OSError, ValueError, ValidationError):
                errors.append({"source": path.name, "code": "ARTIFACT_READ_FAILED"})
    for directory, states in groups.items():
        try:
            latest = max(states, key=lambda p: p.stat().st_mtime) if states else None
            sync_run(directory, latest)
        except (OSError, ValueError, TypeError, ValidationError):
            errors.append({"source": directory.name, "code": "RUN_IMPORT_FAILED"})
    for path in evaluations:
        try:
            import_evaluation(path)
        except (OSError, ValueError, TypeError, ValidationError):
            errors.append({"source": path.name, "code": "EVALUATION_IMPORT_FAILED"})
    return {
        "datasets": DatasetAsset.objects.count(),
        "runs": TrainingRun.objects.count(),
        "evaluations": EvaluationReport.objects.count(),
        "errors": errors,
    }


def run_payload(run):
    progress = (
        min(100, round(run.current_step / run.total_steps * 100, 2)) if run.total_steps else None
    )
    phases = [
        ("data", "数据准备"),
        ("training", "LoRA 微调"),
        ("evaluation", "检索评测"),
        ("approval", "人工确认"),
    ]
    events = set(run.events.values_list("phase", "kind"))
    pipeline = []
    for phase, label in phases:
        status = "not_started"
        evidence = ""
        if (
            phase == "data"
            and DatasetAsset.objects.filter(
                file_status="verified",
                path__in=[
                    run.config.get("data", {}).get("train_file"),
                    run.config.get("data", {}).get("val_file"),
                ],
            ).count()
            == 2
        ):
            status, evidence = (
                "completed",
                "当前训练/验证文件已核验；不据此推断历史训练使用的文件版本",
            )
        elif (
            phase == "evaluation"
            and run.evaluations.filter(source="artifact", verified=True).exists()
        ):
            status, evidence = (
                "completed",
                "已有可读取评测CSV；模型对应关系以指纹清单为准，不代表本机复跑",
            )
        elif (phase, "completed") in events or (
            phase == "approval" and (phase, "approved") in events
        ):
            status = "completed"
        elif phase == "training" and run.status == "early_stopped":
            status = "early_stopped"
        elif phase == run.phase and run.status in {"running", "failed", "interrupted", "ready"}:
            status = run.status
        pipeline.append({"id": phase, "label": label, "status": status, "evidence": evidence})
    return {
        "id": str(run.pk),
        "label": run.label,
        "status": run.status,
        "phase": run.phase,
        "current_step": run.current_step,
        "total_steps": run.total_steps,
        "progress": progress,
        "epoch": run.epoch,
        "metrics": run.metrics,
        "config": run.config,
        "provenance": run.provenance,
        "source": run.source,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "updated_at": run.updated_at,
        "pipeline": pipeline,
    }


def evaluation_payload(report):
    return {
        key: getattr(report, key)
        for key in (
            "id",
            "title",
            "source",
            "verified",
            "scope",
            "metrics",
            "selected_model",
            "sha256",
            "artifacts",
            "updated_at",
        )
    }
