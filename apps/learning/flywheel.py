from __future__ import annotations

import json
import unicodedata

import yaml
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.consultations.models import Feedback
from apps.learning.models import FlywheelBatch, FlywheelCandidate, TrainingRun
from apps.learning.paths import bounded_path, digest, redact
from apps.learning.training import add_event, config, project_path


class ConsentRevoked(APIException):
    status_code = 410
    default_detail = "反馈授权已撤回或标注发生变化；该批次不可继续导出或准备训练"
    default_code = "CONSENT_REVOKED"


def query_hash(text):
    return digest(" ".join(unicodedata.normalize("NFKC", redact(text)).lower().split()))


def feedback_payload(run):
    return (
        run.feedback.filter(user_id=run.consultation.user_id)
        .values("id", "rating", "comment", "training_consent")
        .first()
    )


def refresh_feedback(feedback):
    """Opt-in creates a review candidate; a rating is never a retrieval relevance label."""
    with transaction.atomic():
        feedback = (
            Feedback.objects.select_for_update()
            .select_related("run__message", "run__reply")
            .get(pk=feedback.pk)
        )
        candidate = FlywheelCandidate.objects.filter(feedback=feedback).first()
        eligible = feedback.training_consent and feedback.run.status == "succeeded"
        if not eligible:
            if candidate:
                candidate.status, candidate.fingerprint = "revoked", None
                candidate.save(update_fields=["status", "fingerprint", "updated_at"])
            return candidate
        # Follow-up answers such as "没有用药" are not meaningful BGE queries
        # alone. Retain the same consultation's original user question, never
        # assistant-generated diagnoses or another consultation's history.
        initial = feedback.run.consultation.messages.filter(role="user", pk__lte=feedback.run.message_id).order_by("created_at", "id").values_list("content", flat=True).first()
        current = feedback.run.message.content
        query = redact(initial + "\n" + current if initial and initial != current else current)
        if (
            candidate
            and candidate.feedback_version == feedback.updated_at
            and candidate.status != "revoked"
            and (candidate.status != "pending" or candidate.query_hash == query_hash(query))
        ):
            return candidate
        citations = feedback.run.reply.citations if feedback.run.reply_id else []
        clean_citations = [
            {
                key: redact(value)[:4000] if isinstance(value, str) else value
                for key, value in item.items()
                if key
                in {"id", "chunk_id", "source", "source_id", "document_id", "title", "url", "snippet", "quote", "text", "source_hash", "chunk_hash", "index_version", "authority"}
            }
            for item in citations
            if isinstance(item, dict)
        ]
        candidate, _ = FlywheelCandidate.objects.update_or_create(
            feedback=feedback,
            defaults={
                "status": "pending",
                "query": query,
                "query_hash": query_hash(query),
                "comment": redact(feedback.comment),
                "citations": clean_citations,
                "positive": "",
                "negative": "",
                "positive_source": "",
                "negative_source": "",
                "review_note": "",
                "fingerprint": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "feedback_version": feedback.updated_at,
            },
        )
        return candidate


def candidate_payload(candidate):
    result = {
        key: getattr(candidate, key)
        for key in (
            "id",
            "status",
            "query",
            "query_hash",
            "comment",
            "citations",
            "positive",
            "negative",
            "positive_source",
            "negative_source",
            "review_note",
            "redacted",
            "updated_at",
        )
    }
    result.update(
        {
            "feedback_id": candidate.feedback_id,
            "run_id": str(candidate.feedback.run_id),
            "rating": candidate.feedback.rating,
            "consent": candidate.feedback.training_consent,
        }
    )
    return result


def collect():
    created = updated = 0
    for feedback in Feedback.objects.select_related("run").order_by("pk")[
        : settings.LEARNING_MAX_CANDIDATES
    ]:
        previous = (
            FlywheelCandidate.objects.filter(feedback=feedback).values("feedback_version").first()
        )
        candidate = refresh_feedback(feedback)
        if candidate and not previous:
            created += 1
        elif candidate and previous["feedback_version"] != feedback.updated_at:
            updated += 1
    return {"created": created, "updated": updated}


def review(candidate, data, user):
    with transaction.atomic():
        candidate = (
            FlywheelCandidate.objects.select_for_update()
            .select_related("feedback__run__reply")
            .get(pk=candidate.pk)
        )
        feedback = Feedback.objects.select_for_update().get(pk=candidate.feedback_id)
        if not feedback.training_consent or candidate.feedback_version != feedback.updated_at:
            raise ConsentRevoked()
        decision = data.get("decision")
        if decision not in {"approve", "reject"}:
            raise ValidationError({"decision": "请选择approve或reject"})
        note = str(data.get("review_note", "")).strip()
        if not note or len(note) > 2000:
            raise ValidationError({"review_note": "请填写不超过2000字的标注依据"})
        if decision == "approve":
            if (
                data.get("redaction_confirmed") is not True
                or data.get("evidence_confirmed") is not True
            ):
                raise ValidationError("需人工确认脱敏和相关性证据")
            positive, negative = (
                str(data.get(key, "")).strip() for key in ("positive", "negative")
            )
            sources = [
                str(data.get(key, "")).strip() for key in ("positive_source", "negative_source")
            ]
            if not positive or not negative or query_hash(positive) == query_hash(negative):
                raise ValidationError("正例与负例都需填写且内容不同")
            if max(len(positive), len(negative)) > 20000 or any(
                not source or len(source) > 500 for source in sources
            ):
                raise ValidationError("证据过长或缺少可追溯来源")
            reply = candidate.feedback.run.reply
            if reply and any(
                query_hash(value) == query_hash(reply.content) for value in (positive, negative)
            ):
                raise ValidationError("不能直接把LLM回复当作检索相关性真值，请标注来源文档证据")
            candidate.positive, candidate.negative = redact(positive), redact(negative)
            candidate.positive_source, candidate.negative_source = map(redact, sources)
            candidate.fingerprint = digest(
                [
                    candidate.query_hash,
                    query_hash(candidate.positive),
                    query_hash(candidate.negative),
                ]
            )
            candidate.status = "approved"
        else:
            candidate.status, candidate.fingerprint = "rejected", None
        candidate.review_note = redact(note)
        candidate.reviewed_by, candidate.reviewed_at = user, timezone.now()
        try:
            with transaction.atomic():
                candidate.save()
        except IntegrityError:
            raise ValidationError(
                {"code": "DUPLICATE_LABEL", "detail": "相同查询与证据已标注，不能重复入库"}
            ) from None
    return candidate


def holdout_hashes():
    cfg = config()
    path = bounded_path(
        project_path(cfg["data"]["val_file"]), [project_path(settings.LEARNING_DATA_ROOT)]
    )
    if not path.exists():
        return None
    if path.stat().st_size > settings.LEARNING_MAX_DATASET_BYTES:
        raise ValidationError("验证集超出配置限制")
    hashes = set()
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                hashes.add(query_hash(value.get("query", "")))
    return hashes


def create_batch(data, user):
    ids = data.get("candidate_ids")
    if not isinstance(ids, list) or not ids or len(ids) > settings.LEARNING_MAX_CANDIDATES:
        raise ValidationError("请选择审核通过的样本（数量受配置限制）")
    if any(not isinstance(value, int) or isinstance(value, bool) for value in ids):
        raise ValidationError("样本ID格式错误")
    with transaction.atomic():
        candidates = list(
            FlywheelCandidate.objects.select_for_update()
            .filter(pk__in=ids)
            .select_related("feedback")
            .order_by("id")
        )
        if len(candidates) != len(set(ids)):
            raise ValidationError("样本不存在")
        validation_hashes = holdout_hashes()
        rows = []
        for item in candidates:
            feedback = Feedback.objects.select_for_update().get(pk=item.feedback_id)
            if not feedback.training_consent or feedback.updated_at != item.feedback_version:
                raise ConsentRevoked()
            if item.status != "approved":
                raise ValidationError("只能导出人工审核通过的检索样本")
            if validation_hashes is not None and item.query_hash in validation_hashes:
                raise ValidationError(
                    {
                        "code": "HOLDOUT_OVERLAP",
                        "detail": "存在与既有验证集重叠的查询，请移除后重试",
                    }
                )
            split = (
                "validation"
                if int(item.query_hash[:8], 16) % 100 < settings.LEARNING_VALIDATION_PERCENT
                else "train"
            )
            rows.append(
                {
                    "candidate_id": item.pk,
                    "feedback_id": feedback.pk,
                    "feedback_version": feedback.updated_at.isoformat(),
                    "fingerprint": item.fingerprint,
                    "query_hash": item.query_hash,
                    "query": item.query,
                    "positive": item.positive,
                    "negative": item.negative,
                    "positive_source": item.positive_source,
                    "negative_source": item.negative_source,
                    "split": split,
                }
            )
        fingerprint = digest(rows)
        existing = FlywheelBatch.objects.filter(sha256=fingerprint).first()
        if existing:
            return existing
        return FlywheelBatch.objects.create(
            label=str(data.get("label", "反馈检索训练集"))[:160],
            records=rows,
            sha256=fingerprint,
            created_by=user,
            manifest={
                "version": 1,
                "sample_count": len(rows),
                "train_count": sum(row["split"] == "train" for row in rows),
                "validation_count": sum(row["split"] == "validation" for row in rows),
                "holdout_status": "checked" if validation_hashes is not None else "not_connected",
                "grouping": "NFKC+whitespace+lower+redacted query SHA256",
                "validation_percent": settings.LEARNING_VALIDATION_PERCENT,
                "label_policy": "explicit consent + human-reviewed document relevance; rating is not a label",
                "consent_note": "撤回后禁止未来导出；已下载至外部的文件或已训练模型无法自动追溯删除，需联系训练负责人",
            },
        )


def batch_payload(batch):
    return {
        "id": str(batch.pk),
        "label": batch.label,
        "status": batch.status,
        "sha256": batch.sha256,
        "created_at": batch.created_at,
        "manifest": batch.manifest,
        **{
            key: batch.manifest[key]
            for key in ("sample_count", "train_count", "validation_count", "holdout_status")
        },
    }


def check_batch(batch):
    for row in batch.records:
        candidate = (
            FlywheelCandidate.objects.select_related("feedback")
            .filter(pk=row["candidate_id"])
            .first()
        )
        if (
            candidate is None
            or not candidate.feedback.training_consent
            or candidate.status != "approved"
            or candidate.fingerprint != row["fingerprint"]
            or candidate.feedback.updated_at.isoformat() != row["feedback_version"]
        ):
            raise ConsentRevoked()


def export_rows(batch, format_name="triplets", split="train"):
    check_batch(batch)
    if format_name not in {"triplets", "flagembedding"} or split not in {"train", "validation"}:
        raise ValidationError("不支持的导出格式或数据划分")
    values = []
    for row in batch.records:
        if row["split"] == split:
            value = (
                {"query": row["query"], "positive": row["positive"], "negative": row["negative"]}
                if format_name == "triplets"
                else {"query": row["query"], "pos": [row["positive"]], "neg": [row["negative"]]}
            )
            values.append(json.dumps(value, ensure_ascii=False))
    return ("\n".join(values) + ("\n" if values else "")).encode("utf-8")


def prepare(batch):
    with transaction.atomic():
        batch = FlywheelBatch.objects.select_for_update().get(pk=batch.pk)
        check_batch(batch)
        cfg = config()
        validation_hashes = holdout_hashes()
        if validation_hashes is None and settings.LEARNING_REQUIRE_HOLDOUT:
            raise ValidationError(
                {
                    "code": "VALIDATION_DATA_MISSING",
                    "detail": "现有验证集未接入，禁止跳过防泄漏检查启动训练；请先配置同学的验证数据",
                }
            )
        if validation_hashes is not None and any(
            row["query_hash"] in validation_hashes for row in batch.records
        ):
            raise ValidationError({"code": "HOLDOUT_OVERLAP", "detail": "当前验证集与批次查询重叠"})
        if not batch.manifest["train_count"]:
            raise ValidationError("该批次仅含保留验证样本，没有训练样本")
        root = bounded_path(
            project_path(settings.LEARNING_HANDOFF_ROOT) / "batches" / str(batch.pk),
            [project_path(settings.LEARNING_HANDOFF_ROOT)],
        )
        root.mkdir(parents=True, exist_ok=True)
        train_path = root / "train_triplets.jsonl"
        train_path.write_bytes(export_rows(batch))
        (root / "validation_triplets.jsonl").write_bytes(export_rows(batch, split="validation"))
        (root / "manifest.json").write_text(
            json.dumps({**batch.manifest, "sha256": batch.sha256}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Preserve the colleague's full configuration; override only this run's data/output paths.
        full_cfg = yaml.safe_load(
            project_path(settings.LEARNING_CONFIG_PATH).read_text(encoding="utf-8")
        )
        full_cfg["data"]["train_file"] = str(train_path)
        full_cfg["data"]["use_explicit_negatives"] = True
        full_cfg["train"]["output_dir"] = str(root / "output")
        full_cfg["eval"]["output_csv"] = str(root / "output" / "eval_comparison.csv")
        config_path = root / "training.yaml"
        config_path.write_text(
            yaml.safe_dump(full_cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        if not batch.training_run_id:
            run = TrainingRun.objects.create(
                source_key=digest(str(root / "output")),
                label=batch.label,
                status="ready",
                phase="training",
                config=cfg,
                source=f"batches/{batch.pk}",
            )
            add_event(
                run,
                {
                    "kind": "completed",
                    "phase": "data",
                    "message": "授权、脱敏、证据标注与查询分组检查完成",
                },
            )
            add_event(
                run,
                {
                    "kind": "prepared",
                    "phase": "training",
                    "message": "训练配置已准备，尚未执行GPU训练",
                },
            )
            batch.training_run = run
            batch.save(update_fields=["training_run"])
        command = [
            settings.LEARNING_PYTHON_EXECUTABLE,
            str(settings.BASE_DIR / "scripts/learning_run.py"),
            "--config",
            str(config_path),
            "--run-id",
            str(batch.training_run_id),
            "--batch-id",
            str(batch.pk),
            "--with-eval",
        ]
        display = "& " + " ".join("'" + part.replace("'", "''") + "'" for part in command)
        return {
            "batch_id": str(batch.pk),
            "run_id": str(batch.training_run_id),
            "status": "ready",
            "command": command,
            "command_display": display,
            "shell": "powershell",
            "config_path": str(config_path),
            "training_enabled": False,
            "note": "Web不自动启动GPU任务；在已配置GPU依赖的环境执行命令，产物同步后显示真实训练与评测结果。",
        }
