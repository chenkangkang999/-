#!/usr/bin/env python
"""Django 管理入口。"""
from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django 未安装或虚拟环境未激活。请先执行：\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements\\dev.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
