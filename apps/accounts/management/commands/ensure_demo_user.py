"""确保演示环境存在默认管理员账号。

创空间容器是全新空数据库，migrate 之后没有任何用户，登录会因"用户不存在"失败。
本命令在容器启动时（migrate 之后）调用，幂等地创建/更新一个演示超级用户。

账号/密码可通过环境变量覆盖，默认 admin / admin123。
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "确保演示环境存在默认管理员账号（幂等）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.getenv("DEMO_ADMIN_USERNAME", "admin"),
            help="演示账号用户名",
        )
        parser.add_argument(
            "--password",
            default=os.getenv("DEMO_ADMIN_PASSWORD", "admin123"),
            help="演示账号密码",
        )
        parser.add_argument(
            "--email",
            default=os.getenv("DEMO_ADMIN_EMAIL", ""),
            help="演示账号邮箱",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        user, created = User.objects.get_or_create(username=username)
        user.set_password(options["password"])
        user.email = options["email"]
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()
        action = "创建" if created else "更新"
        self.stdout.write(
            self.style.SUCCESS(f"{action}演示账号: {username}（超级用户，可登录）")
        )
