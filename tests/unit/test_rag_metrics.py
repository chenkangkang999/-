from __future__ import annotations

import pytest

from rag.evaluation.metrics import mrr, ndcg_at_k, recall_at_k

pytestmark = pytest.mark.unit


def test_recall_at_k_counts_hits_within_k():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, ["b", "d"], k=2) == 0.5
    assert recall_at_k(ranked, ["b", "d"], k=4) == 1.0


def test_recall_without_relevant_is_zero():
    assert recall_at_k(["a"], [], k=1) == 0.0


def test_mrr_uses_first_hit_position():
    assert mrr(["x", "y", "z"], ["y"]) == 0.5
    assert mrr(["x"], ["y"]) == 0.0


def test_ndcg_is_one_for_perfect_ranking():
    assert ndcg_at_k(["a", "b"], ["a", "b"], k=2) == pytest.approx(1.0)
    assert ndcg_at_k(["b", "a"], ["a"], k=2) < 1.0
