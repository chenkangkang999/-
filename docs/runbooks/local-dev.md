# 本地开发手册

## 首次启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

## 日常

| 场景 | 命令 |
| --- | --- |
| 起后端 | `.\.venv\Scripts\python.exe manage.py runserver` |
| 起前端 | `cd frontend; npm run dev` |
| 跑测试 | `.\.venv\Scripts\python.exe -m pytest -q` |
| 代码检查 | `.\.venv\Scripts\python.exe -m ruff check .` |
| 建迁移 | `.\.venv\Scripts\python.exe manage.py makemigrations` |
| 起容器栈 | `docker compose -f infra/compose/docker-compose.yml up --build` |

## 常见问题

- **前端 401**：Django 默认 `IsAuthenticated`，先在 `/admin/` 登录，或调整 `REST_FRAMEWORK` 权限。
- **WebSocket 连不上**：需要 `daphne` 启动 ASGI（`pip install -r requirements/base.txt` 已含）。
- **没有 LLM Key**：系统会走 `EchoLLM` 占位，链路仍可演示。