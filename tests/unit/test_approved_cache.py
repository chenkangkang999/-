from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from django.core.cache import cache

from agents.base.context import AgentContext
from apps.consultations.services import approved_cache

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def setup_cache(settings):
    settings.APPROVED_RESPONSE_CACHE_ENABLED = True
    cache.clear()


def run_for(user_id=1, text="什么是血压"):
    return SimpleNamespace(
        consultation=SimpleNamespace(user_id=user_id),
        message=SimpleNamespace(content=text),
        metadata={},
    )


def test_cache_is_user_scoped_and_education_only():
    context = AgentContext(patient={"allergies": []})
    key = approved_cache.key_for(run_for(), context)
    assert key != approved_cache.key_for(run_for(2), context)
    assert approved_cache.key_for(run_for(text="我咳嗽三天"), context) is None
    assert (
        approved_cache.key_for(
            run_for(), AgentContext(facts={"history": [{"role": "user", "content": "病史"}]})
        )
        is None
    )
    explicit = run_for()
    explicit.metadata["intake_submission"] = {"allergies": "青霉素过敏"}
    assert approved_cache.key_for(explicit, context) is None


def test_only_reviewed_payload_can_be_cached_and_integrity_is_checked():
    key = "approved:test"
    approved_cache.store(key, "PRIVATE_UNREVIEWED", {}, [], {"decision": "block"})
    assert cache.get(key) is None
    approved_cache.store(key, "已审核健康知识", {"soap": {}}, [], {"decision": "pass"})
    assert approved_cache.load(key)["text"] == "已审核健康知识"
    changed = json.loads(cache.get(key))
    changed["text"] = "ALTERED"
    cache.set(key, json.dumps(changed))
    assert approved_cache.load(key) is None


def test_cached_payload_is_rechecked_against_current_rules():
    approved_cache.store("unsafe:test", "我是你的主治医生", {}, [], {"decision": "pass"})
    assert approved_cache.load("unsafe:test") is None


def test_custom_prompt_change_invalidates_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROMPTS_DIR", str(tmp_path))
    prompt = tmp_path / "explainer.md"
    prompt.write_text("version-one", encoding="utf-8")
    first = approved_cache.key_for(run_for(), AgentContext())
    prompt.write_text("version-two", encoding="utf-8")
    assert approved_cache.key_for(run_for(), AgentContext()) != first
