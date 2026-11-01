from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rag.models import IndexRun
from apps.rag.services.search import search_with_status


class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "")
        try:
            top_k = int(request.query_params.get("top_k", settings.RAG_TOP_K))
        except (ValueError, TypeError):
            raise ValidationError("top_k必须是有效整数") from None
        if not 1 <= top_k <= settings.RAG_MAX_TOP_K:
            raise ValidationError("top_k超出配置范围")
        outcome = search_with_status(query, top_k, user=request.user)
        return Response({"query": query, "results": [chunk.to_dict() for chunk in outcome.results],
                         **outcome.metadata()}, status=503 if outcome.status == "error" else 200)


class RAGStatusView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from apps.consultations.services.clinical_evidence import clinical_data_status
        from apps.learning.models import DatasetAsset, ModelVersion
        from apps.rag.services.configuration import project_path

        latest = IndexRun.objects.filter(stats__mode=settings.RAG_MODE).first()
        usable = IndexRun.objects.filter(status="succeeded", stats__mode=settings.RAG_MODE).first()
        adapter_consumed = False
        version_error = ""
        if settings.RAG_MODE == "milvus":
            from apps.rag.services.configuration import embedding_state
            from rag.model_backends import RAGUnavailable
            try:
                _, adapter, current_version = embedding_state()
                matching_index = bool(usable and usable.stats.get("model_version") == current_version)
                adapter_consumed = bool(adapter and matching_index)
                if usable and not matching_index:
                    version_error = "MODEL_INDEX_VERSION_MISMATCH"
            except RAGUnavailable as exc:
                version_error = exc.code
        total = None
        if latest and not latest.stats.get("limited"):
            counts = [DatasetAsset.objects.filter(sha256=source["file_sha256"], file_status="verified").values_list("observed_rows", flat=True).first() for source in latest.stats.get("source_files", [])]
            if counts and all(count is not None for count in counts):
                total = sum(counts)
        index = None if latest is None else {
            "id": latest.pk, "status": latest.status, "processed_rows": latest.stats.get("processed_rows", 0),
            "total_rows": total, "documents": latest.document_count, "chunks": latest.chunk_count,
            "deduplicated": latest.skipped_duplicated, "full_corpus": latest.stats.get("full_corpus", False),
            "limited": latest.stats.get("limited", False), "started_at": latest.started_at,
            "finished_at": latest.finished_at, "error_code": latest.stats.get("error_code", ""),
            "corpus_kinds": latest.stats.get("corpus_kinds", []),
        }
        return Response({"mode": settings.RAG_MODE, "status": "connected" if usable and not version_error else "not_connected",
                         "error_code": version_error,
                         "degraded": settings.RAG_MODE == "bm25", "degraded_reason": "当前为真实CPU BM25稀疏检索；BGE/Milvus尚未启用" if settings.RAG_MODE == "bm25" else "",
                         "index": index, "usable_index_id": usable.pk if usable else None,
                         "base_model_present": (project_path(settings.RAG_BASE_MODEL_PATH) / "config.json").is_file(),
                         "model_loading_enabled": settings.RAG_ENABLE_MODEL_LOAD,
                         "active_adapter_registered": ModelVersion.objects.filter(is_active=True).exists(),
                         "active_adapter_consumed": adapter_consumed,
                         "reranker": settings.RAG_RERANKER, "clinical_data": clinical_data_status()})


class IndexStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest = IndexRun.objects.first()
        return Response(
            {
                "latest": None
                if latest is None
                else {
                    "status": latest.status,
                    "documents": latest.document_count,
                    "chunks": latest.chunk_count,
                    "deduplicated": latest.skipped_duplicated,
                    "started_at": latest.started_at,
                }
            }
        )
