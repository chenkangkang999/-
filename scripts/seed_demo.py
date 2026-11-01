"""写入演示数据：账号、价格方案、知识库样例。

用法：python scripts/seed_demo.py（或 .venv 里的 python）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from apps.accounts.models import PatientProfile  # noqa: E402
from apps.billing.models import PricePlan  # noqa: E402
from apps.rag.models import Chunk, Document  # noqa: E402
from rag.dedup.hash import content_hash  # noqa: E402

DOCS = [
    {
        "title": "成人急性咳嗽基层诊疗指南（示例）",
        "authority": Document.Authority.GUIDELINE,
        "source": "示例指南",
        "text": "急性咳嗽多由病毒感染引起，通常 3 周内自愈。出现呼吸困难、咯血、"
                "持续高热或胸痛时，应及时就医排除肺炎等严重疾病。",
        "keywords": "咳嗽 发热 胸痛",
    },
    {
        "title": "高血压患者用药注意事项（示例）",
        "authority": Document.Authority.CONSENSUS,
        "source": "示例共识",
        "text": "服用降压药期间应规律监测血压，避免自行停药；出现头晕、乏力等"
                "低血压表现时应复诊调整剂量。",
        "keywords": "高血压 降压药 头晕",
    },
]


def seed() -> None:
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username="demo", defaults={"email": "demo@example.com"}
    )
    if created:
        user.set_password("demo12345")
        user.save()
    PatientProfile.objects.get_or_create(
        user=user,
        defaults={"display_name": "演示患者", "allergies": ["青霉素"],
                  "chronic_conditions": ["高血压"], "consent_data_use": True},
    )

    PricePlan.objects.get_or_create(
        name="default",
        defaults={"input_per_1k": "0.001", "output_per_1k": "0.002", "currency": "CNY"},
    )

    for item in DOCS:
        digest = content_hash(item["text"])
        document, doc_created = Document.objects.get_or_create(
            content_hash=digest,
            defaults={
                "title": item["title"],
                "source": item["source"],
                "authority": item["authority"],
                "metadata": {"keywords": item["keywords"]},
            },
        )
        if doc_created:
            Chunk.objects.create(document=document, seq=0, text=item["text"],
                                 token_count=len(item["text"]))

    print("演示数据就绪：账号 demo / demo12345")


if __name__ == "__main__":
    seed()
