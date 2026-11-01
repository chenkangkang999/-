import json

from django.core.management.base import BaseCommand

from apps.learning.training import synchronize


class Command(BaseCommand):
    help = "从配置目录核验训练数据并增量同步训练日志和评测产物（不启动训练）"

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(synchronize(), ensure_ascii=False))
