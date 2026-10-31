"""知识库模型：Document → Chunk → 向量 id。

hash 去重落在 Document.content_hash（唯一约束），索引前先查/插。
"""
from __future__ import annotations

from django.db import models


class Document(models.Model):
    class Authority(models.TextChoices):
        GUIDELINE = "guideline", "临床指南"
        CONSENSUS = "consensus", "专家共识"
        PAPER = "paper", "论文"
        TEXTBOOK = "textbook", "教科书"
        WEB = "web", "网络资料"

    title = models.CharField(max_length=256)
    source = models.CharField("来源", max_length=512, blank=True)
    url = models.URLField("原文链接", blank=True)
    published_at = models.DateField("发布时间", null=True, blank=True)
    authority = models.CharField(
        max_length=16, choices=Authority.choices, default=Authority.WEB
    )
    content_hash = models.CharField("内容哈希", max_length=64, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rag_document"
        ordering = ("-created_at",)
        verbose_name = verbose_name_plural = "知识文档"

    def __str__(self) -> str:
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    seq = models.PositiveIntegerField("文档内序号", default=0)
    text = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    embedding_id = models.CharField("向量库主键", max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rag_chunk"
        ordering = ("document", "seq")
        indexes = [models.Index(fields=["document", "seq"])]
        verbose_name = verbose_name_plural = "知识切片"

    def __str__(self) -> str:
        return f"{self.document_id}#{self.seq}"


class IndexRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    document_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    skipped_duplicated = models.PositiveIntegerField("hash 去重跳过", default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "rag_index_run"
        ordering = ("-started_at",)
        verbose_name = verbose_name_plural = "索引任务"
