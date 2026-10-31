# 贡献指南

## 分支模型
- `main`：可演示版本
- `develop`：集成分支
- `feat/<scope>-<topic>`、`fix/<scope>-<topic>`

## 提交信息
遵循 Conventional Commits：`feat(rag): 支持 BM25 稀疏检索`。

## 本地检查
```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

## 代码约定
- 业务逻辑放 `services/`，视图只做参数校验与序列化；
- 新增跨模块能力先定义 Protocol，再接实现；
- 任何配置项必须进 `.env.example` 与 README 表格。