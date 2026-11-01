# 魔搭创空间单容器 CPU 演示版
# 只装运行时依赖（prod.txt 不含 torch / sentence-transformers 等重依赖），镜像约 300~400MB
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements ./requirements
RUN pip install -r requirements/prod.txt

# 复制代码；.dockerignore 已排除 models/ data/ frontend/node_modules/ .git/ 等大目录
COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings.demo \
    APP_RUNTIME=local \
    CONSULTATION_EXECUTOR=sync \
    DJANGO_DEBUG=0

EXPOSE 7860

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py ensure_demo_user && python manage.py collectstatic --noinput && daphne -b 0.0.0.0 -p 7860 config.asgi:application"]
