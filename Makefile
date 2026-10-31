PY := .venv/Scripts/python.exe
ifeq ($(OS),Windows_NT)
	PY := .venv/Scripts/python.exe
else
	PY := .venv/bin/python
endif

.PHONY: help install dev migrate test lint fmt seed docker-up docker-down

help:
	@echo "install    创建虚拟环境并安装依赖"
	@echo "dev        启动 Django 开发服务器"
	@echo "migrate    执行数据库迁移"
	@echo "test       运行测试"
	@echo "lint       ruff 检查"
	@echo "fmt        ruff 格式化"
	@echo "seed       写入演示账号与知识库样例"
	@echo "docker-up  启动完整容器栈"

install:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements/dev.txt

dev:
	$(PY) manage.py runserver 0.0.0.0:8000

migrate:
	$(PY) manage.py makemigrations
	$(PY) manage.py migrate

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff format .

seed:
	$(PY) scripts/seed_demo.py

docker-up:
	docker compose -f infra/compose/docker-compose.yml up --build

docker-down:
	docker compose -f infra/compose/docker-compose.yml down