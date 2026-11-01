from __future__ import annotations

import hashlib
import json
import struct

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.learning.models import ModelActivation, ModelVersion
from apps.learning.paths import bounded_path, digest, redact
from apps.learning.training import add_event, project_path


def adapter_fingerprint(path):
    path = bounded_path(
        path,
        [
            project_path(settings.LEARNING_ARTIFACT_ROOT),
            project_path(settings.LEARNING_HANDOFF_ROOT),
        ],
    )
    config_file, weights = path / "adapter_config.json", path / "adapter_model.safetensors"
    bounded_path(config_file, [path])
    bounded_path(weights, [path])
    if (
        not config_file.is_file()
        or not weights.is_file()
        or config_file.stat().st_size > settings.LEARNING_MAX_IMPORT_BYTES
    ):
        raise ValidationError("缺少真实adapter_config.json或adapter_model.safetensors")
    metadata = json.loads(config_file.read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or metadata.get("peft_type") != "LORA"
        or not weights.stat().st_size
    ):
        raise ValidationError("不是有效的LoRA产物清单")
    with weights.open("rb") as handle:
        header_size = handle.read(8)
        if len(header_size) != 8:
            raise ValidationError("safetensors头不完整")
        header_length = struct.unpack("<Q", header_size)[0]
        if (
            not 2 <= header_length <= settings.LEARNING_MAX_IMPORT_BYTES
            or 8 + header_length > weights.stat().st_size
        ):
            raise ValidationError("safetensors头大小无效")
        try:
            header = json.loads(handle.read(header_length))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("safetensors格式无效") from None
        payload_size = weights.stat().st_size - 8 - header_length
        tensors = (
            [value for key, value in header.items() if key != "__metadata__"]
            if isinstance(header, dict)
            else []
        )
        if not tensors or any(
            not isinstance(value, dict)
            or not isinstance(value.get("data_offsets"), list)
            or len(value["data_offsets"]) != 2
            or not all(isinstance(offset, int) for offset in value["data_offsets"])
            or not 0 <= value["data_offsets"][0] < value["data_offsets"][1] <= payload_size
            for value in tensors
        ):
            raise ValidationError("safetensors张量边界无效")
    hashed = hashlib.sha256()
    with weights.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hashed.update(chunk)
    return path, digest([metadata, hashed.hexdigest()])


def register(run, label, adapter_path):
    if (
        run.status not in {"completed", "early_stopped"}
        or not run.evaluations.filter(source="artifact", verified=True).exists()
    ):
        raise ValidationError("需要该运行实际完成并导入关联评测CSV，报告表中的数值不能代替产物")
    path, fingerprint = adapter_fingerprint(adapter_path)
    if not run.artifact_path or not path.is_relative_to(project_path(run.artifact_path).resolve()):
        raise ValidationError("adapter不属于该训练运行的产物目录")
    verified = run.evaluations.filter(
        source="artifact", verified=True, artifacts__adapter_sha256=fingerprint
    ).exists()
    version, _ = ModelVersion.objects.update_or_create(
        sha256=fingerprint,
        defaults={
            "run": run,
            "label": redact(label or run.label)[:160],
            "adapter_path": str(path),
            "validation_status": "evaluated" if verified else "unverified",
        },
    )
    return version


def activate(version, user, note, confirmed):
    if not confirmed or not isinstance(note, str) or not note.strip() or len(note) > 2000:
        raise ValidationError("请人工确认评测证据并填写启用/回滚理由")
    if (
        version.validation_status != "evaluated"
        or not version.run.evaluations.filter(
            source="artifact", verified=True, artifacts__adapter_sha256=version.sha256
        ).exists()
    ):
        raise ValidationError(
            "该候选缺少匹配adapter指纹的实际评测清单；请重新评测，不可用其他checkpoint的指标启用"
        )
    _, fingerprint = adapter_fingerprint(version.adapter_path)
    if fingerprint != version.sha256:
        raise ValidationError("模型文件发生变化，需重新登记和评估")
    with transaction.atomic():
        # Lock a stable row even for the very first activation.
        ModelVersion.objects.select_for_update().order_by("id").first()
        previous = ModelVersion.objects.select_for_update().filter(is_active=True).first()
        if previous and previous.pk == version.pk:
            raise ValidationError("该版本已启用")
        ModelVersion.objects.filter(is_active=True).update(is_active=False)
        version.is_active = True
        version.save(update_fields=["is_active"])
        entry = ModelActivation.objects.create(
            version=version, previous=previous, user=user, review_note=redact(note)
        )
        add_event(
            version.run,
            {
                "kind": "approved",
                "phase": "approval",
                "message": "操作员确认评测证据并启用此模型版本",
            },
        )
    return entry


def rollback(entry, user, note):
    if not entry.previous_id:
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise ValidationError("请填写回滚理由")
        with transaction.atomic():
            ModelVersion.objects.select_for_update().order_by("id").first()
            if not ModelVersion.objects.filter(pk=entry.version_id, is_active=True).exists():
                raise ValidationError("当前活动版本与记录不一致")
            ModelVersion.objects.filter(is_active=True).update(is_active=False)
            return ModelActivation.objects.create(
                version=None, previous=entry.version, user=user, review_note=redact(note)
            )
    if not ModelVersion.objects.filter(pk=entry.version_id, is_active=True).exists():
        raise ValidationError("当前活动版本与该记录不一致，请刷新后重试")
    return activate(entry.previous, user, note, True)


def active_adapter():
    """Retrieval providers opt in to this port; no automatic reload during training."""
    active = ModelVersion.objects.filter(is_active=True).first()
    if active is None:
        return None
    path, fingerprint = adapter_fingerprint(active.adapter_path)
    if fingerprint != active.sha256:
        raise ValidationError("活动模型产物校验失败")
    return str(path)


def version_payload(version):
    return {
        "id": str(version.pk),
        "run_id": str(version.run_id),
        "label": version.label,
        "adapter_path": version.adapter_path,
        "sha256": version.sha256,
        "is_active": version.is_active,
        "validation_status": version.validation_status,
        "created_at": version.created_at,
    }


def activation_payload(entry):
    return {
        "id": entry.pk,
        "previous_id": str(entry.previous_id) if entry.previous_id else None,
        "version_id": str(entry.version_id) if entry.version_id else None,
        "review_note": entry.review_note,
        "created_at": entry.created_at,
    }
