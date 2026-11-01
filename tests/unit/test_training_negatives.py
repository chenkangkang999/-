from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from scripts.train_lora import build_pairs_dataset

pytestmark = pytest.mark.unit


@pytest.fixture
def dataset_factory(monkeypatch):
    class Dataset:
        @staticmethod
        def from_list(rows):
            return rows

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(Dataset=Dataset))


def test_existing_training_stays_pairs_by_default(dataset_factory):
    samples = [{"query": "问题", "positive": "相关证据", "negative": "无关证据"}]
    assert build_pairs_dataset(samples) == [{"anchor": "问题", "positive": "相关证据"}]
    assert samples[0]["negative"] == "无关证据"


def test_opt_in_keeps_reviewed_hard_negative_as_third_input(dataset_factory):
    samples = [{"query": "问题", "positive": "相关证据", "negative": "已审核的难负例"}]
    dataset = build_pairs_dataset(samples, use_explicit_negatives=True)
    assert list(dataset[0]) == ["anchor", "positive", "negative"]
    assert dataset[0]["negative"] == "已审核的难负例"


@pytest.mark.parametrize("negative", [None, "", "  \n\t", 42, False])
def test_invalid_hard_negative_is_rejected_before_dataset_creation(negative):
    samples = [{"query": "问题", "positive": "相关证据", "negative": negative}]
    with pytest.raises(ValueError, match="样本 1 缺少非空 negative"):
        build_pairs_dataset(samples, use_explicit_negatives=True)


def test_every_row_must_have_a_hard_negative():
    samples = [
        {"query": "问题1", "positive": "相关1", "negative": "无关1"},
        {"query": "问题2", "positive": "相关2"},
    ]
    with pytest.raises(ValueError, match="样本 2 缺少非空 negative"):
        build_pairs_dataset(samples, use_explicit_negatives=True)


def test_text_false_is_not_accepted_as_an_enabled_switch():
    with pytest.raises(ValueError, match="必须是布尔值"):
        build_pairs_dataset([], use_explicit_negatives="false")


def test_observation_is_opt_in_and_does_not_import_gpu_dependencies(monkeypatch):
    import scripts.train_lora as trainer

    def reject_import(name):
        raise AssertionError(f"Unexpected observation dependency import: {name}")

    monkeypatch.setattr(trainer.importlib, "import_module", reject_import)
    assert trainer.observation_callbacks({}) == []
    assert trainer.observation_callbacks({"observation": {"enabled": False}}) == []


@pytest.mark.parametrize("package,module_name", [("scripts", "scripts.learning_callbacks"), (None, "learning_callbacks")])
def test_observation_callback_supports_module_and_cli_entry(monkeypatch, package, module_name):
    import scripts.train_lora as trainer

    class Callback:
        pass

    monkeypatch.setattr(trainer, "__package__", package)
    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(TrainingObservationCallback=Callback))
    assert isinstance(trainer.observation_callbacks({"observation": {"enabled": True}})[0], Callback)
