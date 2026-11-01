from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.consultations.services.clinical_schema import input_schema


class ClinicalInputSchemaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(input_schema())
