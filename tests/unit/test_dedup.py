from __future__ import annotations

import pytest

from rag.dedup.hash import content_hash, normalize_text

pytestmark = pytest.mark.unit


def test_normalize_collapses_whitespace_and_case():
    assert normalize_text("  Hello   World \n") == "hello world"


def test_same_content_different_spacing_hashes_equal():
    assert content_hash("咳嗽 三天") == content_hash("  咳嗽   三天  ")


def test_different_content_hashes_differ():
    assert content_hash("咳嗽三天") != content_hash("发热三天")
