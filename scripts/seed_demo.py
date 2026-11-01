"""Create a local review account using caller-supplied credentials; no synthetic medical data."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--staff", action="store_true")
    args = parser.parse_args()
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password

    password = getpass.getpass("设置本地账号密码（不回显）：")
    validate_password(password)
    user_model = get_user_model()
    if user_model.objects.filter(username=args.username).exists():
        parser.error("账号已存在；请通过管理后台修改，不自动重置密码。")
    user_model.objects.create_user(
        username=args.username,
        password=password,
        is_staff=args.staff,
        is_superuser=args.staff,
    )
    print("本地账号已创建。知识库、价格和预算需要由负责人配置，不注入模拟数据。")


if __name__ == "__main__":
    main()
