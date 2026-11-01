import json

from django.core.management.base import BaseCommand

from apps.consultations.services.clinical_evidence import import_evidence


class Command(BaseCommand):
    help = "按配置校验并索引NMPA别名、DDInter药对与人工核验的指南/说明书，不加载模型或pickle"

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(import_evidence(), ensure_ascii=False))
