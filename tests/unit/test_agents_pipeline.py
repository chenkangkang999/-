from __future__ import annotations

import pytest

from agents.base.coordinator import Coordinator

pytestmark = pytest.mark.unit


def test_pipeline_runs_all_agents_and_flags_red_flag():
    result = Coordinator().run("胸痛，呼吸困难，持续十分钟")
    names = [step["agent"] for step in result.steps]
    assert names[:2] == ["triage", "retrieval"]
    assert "risk" in names and "medication" in names
    assert "explainer" in names and "safety" in names
    assert result.risk_level == "high"
    assert "急诊" in result.reply or "立即" in result.reply


def test_reply_contains_disclaimer_when_safety_runs():
    result = Coordinator().run("最近有点咳嗽")
    assert "不构成" in result.reply or "不替代" in result.reply or "急诊" in result.reply
