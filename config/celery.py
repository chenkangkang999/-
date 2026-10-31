"""Celery 应用入口（broker/backend 走环境变量）。"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("medconsult")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.task_routes = {
    "apps.rag.tasks.*": {"queue": "indexing"},
    "apps.monitoring.tasks.*": {"queue": "metrics"},
}


@app.task(bind=True, name="config.ping")
def ping(self) -> str:
    return "pong"
