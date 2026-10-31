from django.contrib import admin

from apps.rag.models import Chunk, Document, IndexRun


class ChunkInline(admin.TabularInline):
    model = Chunk
    extra = 0


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "authority", "published_at", "created_at")
    list_filter = ("authority",)
    search_fields = ("title", "source")
    inlines = [ChunkInline]


@admin.register(IndexRun)
class IndexRunAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "document_count", "chunk_count", "skipped_duplicated",
                    "started_at")
