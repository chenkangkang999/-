from __future__ import annotations

import json
import os
import re
import struct
import uuid
import zipfile

import pytest
import yaml
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.consultations.models import Consultation, ConsultationRun, Feedback, Message
from apps.learning import flywheel, registry, training
from apps.learning.models import (
    DatasetAsset,
    EvaluationReport,
    FlywheelCandidate,
    TrainingEvent,
    TrainingRun,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(django_user_model):
    return django_user_model.objects.create_user(username="learning-reviewer", is_staff=True)


@pytest.fixture
def client(operator):
    api = APIClient()
    api.force_authenticate(operator)
    return api


@pytest.fixture
def storage(tmp_path, settings):
    data, artifacts, handoff = (tmp_path / name for name in ("data", "artifacts", "handoff"))
    for path in (data, artifacts, handoff):
        path.mkdir()
    validation = data / "val.jsonl"
    validation.write_text(
        json.dumps({"query": "固定离线验证集查询", "positive": "指南", "negative": "不相关"})
        + "\n",
        encoding="utf-8",
    )
    cfg = {
        "model": {"model_id": "test-bge", "local_dir": str(tmp_path / "model")},
        "data": {
            "train_file": str(data / "train.jsonl"),
            "val_file": str(validation),
            "max_train_samples": 0,
        },
        "lora": {"r": 16},
        "train": {
            "output_dir": str(artifacts / "output"),
            "num_epochs": 1,
            "lr_scheduler_type": "linear",
            "weight_decay": 0,
            "early_stopping": False,
        },
        "eval": {
            "num_negatives": 19,
            "top_ks": [1, 5, 10],
            "output_csv": str(artifacts / "eval_comparison.csv"),
        },
    }
    config_path = tmp_path / "training.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    manifest = {
        "source": "test report",
        "selected_profile": {"id": "baseline"},
        "datasets": [
            {
                "key": "training",
                "title": "训练集",
                "source": "test",
                "path": str(data / "train.jsonl"),
                "format": "jsonl",
                "reported_rows": 90000,
            }
        ],
        "reported_evaluation": {
            "title": "同学报告",
            "selected_model": "baseline",
            "scope": {"kind": "candidate_pool", "candidates": 20},
            "metrics": [{"metric": "Recall@1", "base": 0.8, "baseline": 0.9}],
        },
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    settings.LEARNING_CONFIG_PATH = config_path
    settings.LEARNING_MANIFEST_PATH = manifest_path
    settings.LEARNING_DATA_ROOT = data
    settings.LEARNING_ARTIFACT_ROOT = artifacts
    settings.LEARNING_HANDOFF_ROOT = handoff
    settings.LEARNING_VALIDATION_PERCENT = 1
    return data, artifacts, handoff


def feedback_for(user, *, consent=True, text="咳嗽三天，手机13812345678", rating=-1):
    consultation = Consultation.objects.create(user=user)
    message = Message.objects.create(consultation=consultation, role="user", content=text)
    reply = Message.objects.create(
        consultation=consultation,
        role="assistant",
        content="安全审核后的解释",
        citations=[
            {"source_id": "guide-a", "snippet": "指南证据", "url": "https://example.org/guide"}
        ],
    )
    run = ConsultationRun.objects.create(
        consultation=consultation,
        message=message,
        reply=reply,
        status="succeeded",
        client_request_id=uuid.uuid4(),
        trace_id=uuid.uuid4().hex,
    )
    return Feedback.objects.create(
        user=user, consultation=consultation, run=run, rating=rating, training_consent=consent
    )


def approve(feedback, operator, positive="呼吸道指南的相关段落", negative="骨科指南的不相关段落"):
    candidate = flywheel.refresh_feedback(feedback)
    return flywheel.review(
        candidate,
        {
            "decision": "approve",
            "positive": positive,
            "negative": negative,
            "positive_source": "clinical-guide:respiratory:1",
            "negative_source": "clinical-guide:orthopaedics:1",
            "review_note": "已人工核对查询和原始指南相关性",
            "redaction_confirmed": True,
            "evidence_confirmed": True,
        },
        operator,
    )


def test_learning_requires_staff_and_csrf(storage, operator, django_user_model):
    api = APIClient(enforce_csrf_checks=True)
    assert api.get("/api/v1/learning/overview/").status_code == 403
    ordinary = django_user_model.objects.create_user(username="ordinary")
    api.force_authenticate(ordinary)
    assert api.get("/api/v1/learning/datasets/").status_code == 403
    api.force_authenticate(user=None)
    api.force_login(operator)
    assert api.post("/api/v1/learning/sync/", {}, format="json").status_code == 403


def test_reported_metrics_and_missing_files_are_distinct(storage, client):
    training.ensure_manifest()
    assets = client.get("/api/v1/learning/datasets/").json()["results"]
    assert assets[0]["reported_rows"] == 90000
    assert assets[0]["observed_rows"] is None
    assert assets[0]["file_status"] == "missing"
    report = client.get("/api/v1/learning/evaluations/").json()["results"][0]
    assert report["source"] == "document_reported" and report["verified"] is False
    assert client.get("/api/v1/learning/runs/").json() == {"results": []}


def test_sync_verifies_actual_rows_not_reported_count(storage, client):
    data, _, _ = storage
    (data / "train.jsonl").write_text('{"query":"one"}\n{"query":"two"}\n', encoding="utf-8")
    response = client.post("/api/v1/learning/sync/", {}, format="json")
    assert response.status_code == 200
    asset = DatasetAsset.objects.get(key="training")
    assert asset.observed_rows == 2 and asset.reported_rows == 90000
    assert asset.file_status == "verified" and len(asset.sha256) == 64
    assert (
        client.post("/api/v1/learning/sync/", {"path": "../../.env"}, format="json").status_code
        == 400
    )


def test_dataset_path_traversal_is_rejected(storage):
    asset = DatasetAsset.objects.create(
        key="bad", title="bad", source="test", path=".env", format="jsonl"
    )
    with pytest.raises(ValidationError):
        training.verify_dataset(asset)


def test_real_hf_logs_are_idempotent_and_do_not_imply_running(storage, client):
    _, root, _ = storage
    checkpoint = root / "baseline" / "checkpoint-20"
    checkpoint.mkdir(parents=True)
    (checkpoint / "trainer_state.json").write_text(
        json.dumps(
            {
                "global_step": 20,
                "max_steps": 100,
                "epoch": 0.2,
                "log_history": [
                    {"step": 10, "loss": 0.7, "prompt": "never publish"},
                    {"step": 20, "eval_loss": 0.3},
                ],
            }
        ),
        encoding="utf-8",
    )
    training.synchronize()
    training.synchronize()
    run = TrainingRun.objects.get()
    assert run.status == "unknown"
    assert TrainingEvent.objects.count() == 2
    payload = client.get(f"/api/v1/learning/runs/{run.pk}/").json()
    assert payload["progress"] == 20
    events = client.get(f"/api/v1/learning/runs/{run.pk}/events/").json()
    assert "never publish" not in str(events)
    assert (
        client.get(f"/api/v1/learning/runs/{run.pk}/events/?after={events['next_cursor']}").json()[
            "results"
        ]
        == []
    )


def test_wrapper_status_failure_and_stale_running(storage, settings):
    _, root, _ = storage
    directory = root / "observed"
    directory.mkdir()
    state = directory / "training_run.json"
    state.write_text(
        json.dumps(
            {"status": "failed", "phase": "training", "current_step": 15, "total_steps": 30}
        ),
        encoding="utf-8",
    )
    training.synchronize()
    assert TrainingRun.objects.get().status == "failed"
    state.write_text(json.dumps({"status": "running"}), encoding="utf-8")
    os.utime(state, (0, 0))
    training.synchronize()
    assert TrainingRun.objects.get().status == "unknown"


def test_nonconsenting_feedback_never_enters_training(storage, operator):
    feedback = feedback_for(operator, consent=False)
    assert flywheel.refresh_feedback(feedback) is None
    assert not FlywheelCandidate.objects.exists()


def test_multiturn_candidate_retains_question_and_citation_identity(storage, operator):
    consultation = Consultation.objects.create(user=operator)
    Message.objects.create(consultation=consultation, role="user", content="咳嗽3天，电话13812345678")
    Message.objects.create(consultation=consultation, role="assistant", content="内部回复不进入查询")
    message = Message.objects.create(consultation=consultation, role="user", content="没有用药")
    reply = Message.objects.create(consultation=consultation, role="assistant", content="审核后回复", citations=[{"chunk_id": "real-chunk", "source": "public-corpus", "quote": "证据"}])
    run = ConsultationRun.objects.create(consultation=consultation, message=message, reply=reply, status="succeeded", client_request_id=uuid.uuid4())
    feedback = Feedback.objects.create(user=operator, consultation=consultation, run=run, rating=1, training_consent=True)
    candidate = flywheel.refresh_feedback(feedback)
    assert "咳嗽3天" in candidate.query and "没有用药" in candidate.query
    assert "13812345678" not in candidate.query and "内部回复" not in candidate.query
    assert candidate.citations[0]["chunk_id"] == "real-chunk"
    assert candidate.citations[0]["source"] == "public-corpus"


def test_dislike_requires_evidence_review_and_redaction(storage, operator):
    feedback = feedback_for(operator)
    candidate = flywheel.refresh_feedback(feedback)
    assert candidate.status == "pending" and candidate.positive == "" and candidate.negative == ""
    assert "13812345678" not in candidate.query
    with pytest.raises(ValidationError):
        flywheel.review(
            candidate, {"decision": "approve", "review_note": "only thumbs down"}, operator
        )
    candidate = approve(feedback, operator)
    assert candidate.status == "approved" and candidate.reviewed_by == operator


def test_llm_reply_is_not_a_retrieval_label(storage, operator):
    feedback = feedback_for(operator)
    with pytest.raises(ValidationError):
        approve(feedback, operator, positive=feedback.run.reply.content)


def test_duplicate_query_and_document_labels_cannot_repeat(storage, operator):
    approve(feedback_for(operator), operator)
    with pytest.raises(ValidationError):
        approve(feedback_for(operator), operator)


def test_frozen_export_consumes_hard_negative_and_revocation_blocks_it(storage, operator):
    feedback = feedback_for(operator)
    candidate = approve(feedback, operator)
    batch = flywheel.create_batch({"candidate_ids": [candidate.pk]}, operator)
    assert flywheel.create_batch({"candidate_ids": [candidate.pk]}, operator).pk == batch.pk
    output = flywheel.export_rows(batch, split=batch.records[0]["split"])
    value = json.loads(output)
    assert value["negative"] == candidate.negative
    flags = json.loads(flywheel.export_rows(batch, "flagembedding", batch.records[0]["split"]))
    assert flags["pos"] == [candidate.positive] and flags["neg"] == [candidate.negative]
    feedback.training_consent = False
    feedback.save()
    flywheel.refresh_feedback(feedback)
    with pytest.raises(flywheel.ConsentRevoked):
        flywheel.export_rows(batch)
    with pytest.raises(flywheel.ConsentRevoked):
        flywheel.prepare(batch)


def test_validation_overlap_is_blocked(storage, operator):
    candidate = approve(feedback_for(operator, text="固定离线验证集查询"), operator)
    with pytest.raises(ValidationError):
        flywheel.create_batch({"candidate_ids": [candidate.pk]}, operator)


def test_prepare_is_ready_not_trained_and_enables_explicit_negatives(storage, operator):
    candidate = approve(feedback_for(operator), operator)
    batch = flywheel.create_batch({"candidate_ids": [candidate.pk]}, operator)
    prepared = flywheel.prepare(batch)
    assert prepared["status"] == "ready" and prepared["training_enabled"] is False
    cfg = yaml.safe_load(open(prepared["config_path"], encoding="utf-8"))
    assert cfg["data"]["use_explicit_negatives"] is True
    assert cfg["train"]["lr_scheduler_type"] == "linear"
    assert cfg["train"]["num_epochs"] == 1 and cfg["train"]["weight_decay"] == 0
    assert TrainingRun.objects.get().status == "ready"


def test_prepare_rejects_missing_holdout(storage, operator):
    candidate = approve(feedback_for(operator), operator)
    batch = flywheel.create_batch({"candidate_ids": [candidate.pk]}, operator)
    (storage[0] / "val.jsonl").unlink()
    with pytest.raises(ValidationError):
        flywheel.prepare(batch)


def write_adapter(path, weight=0.0):
    path.mkdir(parents=True)
    (path / "adapter_config.json").write_text('{"peft_type":"LORA","r":16}', encoding="utf-8")
    header = json.dumps({"lora_A": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    (path / "adapter_model.safetensors").write_bytes(
        struct.pack("<Q", len(header)) + header + struct.pack("<f", weight)
    )


def test_model_registration_requires_real_artifacts_and_linked_eval(storage, operator):
    run = TrainingRun.objects.create(
        source_key="registry", label="test", status="completed", artifact_path=str(storage[1])
    )
    path = storage[1] / "final"
    write_adapter(path)
    with pytest.raises(ValidationError):
        registry.register(run, "baseline", str(path))
    _, fingerprint = registry.adapter_fingerprint(path)
    EvaluationReport.objects.create(
        source_key="actual",
        run=run,
        title="actual",
        source="artifact",
        verified=True,
        artifacts={"adapter_sha256": fingerprint},
    )
    version = registry.register(run, "baseline", str(path))
    assert version.is_active is False and registry.active_adapter() is None
    registry.activate(version, operator, "人工核对实际评测CSV", True)
    assert registry.active_adapter() == str(path)
    (path / "adapter_model.safetensors").write_bytes(b"corrupted")
    with pytest.raises(ValidationError):
        registry.active_adapter()


def test_csv_artifact_links_to_its_real_training_run(storage):
    directory = storage[1] / "observed"
    directory.mkdir()
    (directory / "training_run.json").write_text(
        '{"status":"completed","phase":"evaluation"}', encoding="utf-8"
    )
    (directory / "eval_comparison.csv").write_text(
        "metric,base,lora,delta\nRecall@1,0.7,0.8,0.1\n", encoding="utf-8"
    )
    training.synchronize()
    report = EvaluationReport.objects.get(source="artifact")
    assert report.run_id == TrainingRun.objects.get().pk
    assert report.metrics[0]["baseline"] == 0.8


def test_early_stop_uses_actual_fraction_and_its_own_configuration(storage):
    directory = storage[1] / "cosine"
    directory.mkdir()
    (directory / "training_run.json").write_text(
        json.dumps(
            {
                "status": "early_stopped",
                "config": {"train": {"lr_scheduler_type": "cosine", "num_epochs": 2}},
            }
        ),
        encoding="utf-8",
    )
    (directory / "trainer_state.json").write_text(
        '{"global_step":1200,"max_steps":2500,"epoch":0.96}', encoding="utf-8"
    )
    training.synchronize()
    payload = training.run_payload(TrainingRun.objects.get())
    assert payload["status"] == "early_stopped" and payload["progress"] == 48
    assert payload["config"]["train"]["lr_scheduler_type"] == "cosine"
    assert training.config()["train"]["lr_scheduler_type"] == "linear"


def test_missing_adapter_fingerprint_prevents_activation(storage, operator):
    run = TrainingRun.objects.create(
        source_key="candidate",
        label="historical",
        status="early_stopped",
        artifact_path=str(storage[1]),
    )
    adapter = storage[1] / "checkpoint-1200"
    write_adapter(adapter)
    EvaluationReport.objects.create(
        source_key="legacy-csv", run=run, title="historical", source="artifact", verified=True
    )
    version = registry.register(run, "历史候选", str(adapter))
    assert version.validation_status == "unverified"
    with pytest.raises(ValidationError):
        registry.activate(version, operator, "看到别的checkpoint指标也不能跳过指纹验证", True)


def test_first_model_activation_can_roll_back_to_configured_default(storage, operator):
    run = TrainingRun.objects.create(
        source_key="rollback", label="actual", status="completed", artifact_path=str(storage[1])
    )
    adapter = storage[1] / "final"
    write_adapter(adapter)
    _, fingerprint = registry.adapter_fingerprint(adapter)
    EvaluationReport.objects.create(
        source_key="rollback-eval",
        run=run,
        title="actual",
        source="artifact",
        verified=True,
        artifacts={"adapter_sha256": fingerprint},
    )
    version = registry.register(run, "candidate", str(adapter))
    first = registry.activate(version, operator, "核对实际评测，人工启用", True)
    reverted = registry.rollback(first, operator, "恢复配置默认模型")
    assert reverted.version is None and reverted.previous == version
    assert registry.active_adapter() is None


def test_bundle_import_skips_pickle_and_is_idempotent(storage, tmp_path, monkeypatch):
    from scripts import learning_import_bundle

    bundle = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("bundle/trainer_state.json", '{"global_step":4,"max_steps":10}')
        archive.writestr("bundle/optimizer.pt", "must never load")
    monkeypatch.setattr(
        "sys.argv", ["learning_import_bundle", "--archive", str(bundle), "--run-name", "safe"]
    )
    learning_import_bundle.main()
    learning_import_bundle.main()
    assert (storage[1] / "safe" / "trainer_state.json").exists()
    assert not (storage[1] / "safe" / "optimizer.pt").exists()
    assert TrainingRun.objects.count() == 1


def test_bundle_path_traversal_does_not_escape(storage, tmp_path, monkeypatch):
    from scripts import learning_import_bundle

    bundle = tmp_path / "bad.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.json", "{}")
    monkeypatch.setattr(
        "sys.argv", ["learning_import_bundle", "--archive", str(bundle), "--run-name", "bad"]
    )
    with pytest.raises(ValueError, match="Unsafe archive entry"):
        learning_import_bundle.main()
    assert not (tmp_path / "escape.json").exists()


def test_identical_feedback_retry_does_not_invalidate_review(storage, operator, client):
    feedback = feedback_for(operator)
    candidate = approve(feedback, operator)
    previous_version = feedback.updated_at
    path = f"/api/v1/consultations/{feedback.consultation_id}/feedback/"
    payload = {
        "run_id": str(feedback.run_id),
        "rating": feedback.rating,
        "comment": feedback.comment,
        "training_consent": True,
    }
    assert client.post(path, payload, format="json").status_code == 200
    feedback.refresh_from_db()
    candidate.refresh_from_db()
    assert feedback.updated_at == previous_version and candidate.status == "approved"


def test_page_gets_never_initialize_or_write_database(storage, client):
    paths = ["overview", "datasets", "evaluations"]
    with CaptureQueriesContext(connection) as captured:
        responses = [client.get(f"/api/v1/learning/{path}/") for path in paths]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["sync_required"] is True
    assert responses[1].json()["results"] == responses[2].json()["results"] == []
    assert not DatasetAsset.objects.exists() and not EvaluationReport.objects.exists()
    assert not any(
        re.match(r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b", query["sql"], re.I)
        for query in captured
    )
    training.synchronize()
    with CaptureQueriesContext(connection) as captured:
        responses = [client.get(f"/api/v1/learning/{path}/") for path in paths * 4]
    assert all(response.status_code == 200 for response in responses)
    assert not responses[0].json()["sync_required"]
    assert not any(
        re.match(r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b", query["sql"], re.I)
        for query in captured
    )


def test_preview_is_bounded_redacted_and_rejects_arbitrary_paths(storage, client):
    cache.clear()
    source = storage[0] / "train.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(
                {
                    "query": f"咳嗽{i}，13812345678，tester@example.org",
                    "positive": "指南" * 500,
                    "negative": "不相关",
                },
                ensure_ascii=False,
            )
            for i in range(8)
        ),
        encoding="utf-8",
    )
    training.synchronize()
    path = "/api/v1/learning/datasets/training/preview/"
    response = client.get(path + "?limit=3")
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    value = response.json()
    assert value["asset_key"] == "training" and value["sampled_rows"] == 3
    assert (
        "13812345678" not in response.content.decode()
        and "tester@example.org" not in response.content.decode()
    )
    assert len(value["results"][0]["positive"]) <= 500
    assert client.get(path + "?limit=999").status_code == 400
    assert client.get(path + "?path=.env").status_code == 400
    source.write_text('{"query":"changed"}\n', encoding="utf-8")
    assert client.get(path).status_code == 409
    source.unlink()
    assert client.get(path).status_code == 404


def test_preview_permissions_limits_and_throttle(
    storage, operator, settings, client, django_user_model
):
    cache.clear()
    source = storage[0] / "train.jsonl"
    source.write_text('{"query":"test"}\n', encoding="utf-8")
    training.synchronize()
    path = "/api/v1/learning/datasets/training/preview/"
    anonymous = APIClient()
    assert anonymous.get(path).status_code == 403
    ordinary = django_user_model.objects.create_user(username="preview-not-staff")
    anonymous.force_authenticate(ordinary)
    assert anonymous.get(path).status_code == 403
    settings.LEARNING_PREVIEW_RATE = "1/min"
    assert client.get(path).status_code == 200
    assert client.get(path).status_code == 429
    cache.clear()
    settings.LEARNING_PREVIEW_RATE = "30/min"
    settings.LEARNING_PREVIEW_LINE_BYTES = 4
    assert client.get(path).status_code == 413


def test_preview_asset_cannot_point_outside_data_root(storage, client):
    cache.clear()
    training.synchronize()
    asset = DatasetAsset.objects.get(key="training")
    asset.path = ".env"
    asset.save(update_fields=["path"])
    assert client.get("/api/v1/learning/datasets/training/preview/").status_code == 400
