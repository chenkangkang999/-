"""Django 项目配置包；提前加载 Celery 应用，保证 @shared_task 可用。"""
from __future__ import annotations

from config.celery import app as celery_app

__all__ = ("celery_app",)
