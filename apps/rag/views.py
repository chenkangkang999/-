from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rag.models import IndexRun
from apps.rag.services.search import search_chunks


class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "")
        top_k = min(int(request.query_params.get("top_k", 5)), 20)
        results = [chunk.to_dict() for chunk in search_chunks(query, top_k=top_k)]
        return Response({"query": query, "results": results})


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
