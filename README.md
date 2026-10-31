# 医疗问诊多智能体协作系统

> 协调器（Coordinator）+ 多专职 Agent 的医疗问诊协作系统：问诊 → 检索 → 用药 → 风险评估 → 辩论仲裁 → 白话解释 → 安全护栏，配套监控面板与计费。

**定位**：答辩项目 / 可演示的工程骨架。AI 输出不构成诊断或处方，最终结论以执业医师为准。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Django 5 + DRF + Django Channels（WebSocket） |
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + ECharts |
| 业务库 | PostgreSQL（本地默认 SQLite，零配置启动） |
| 缓存/队列 | Redis + Celery |
| 向量库 | Milvus（P2 接入；当前检索有 SQL 兜底实现） |
| 多智能体 | 自研 BaseAgent / Coordinator（LangGraph 辩论编排在 P3 接入） |
| LLM | OpenAI 兼容 API；未配 Key 时自动降级为离线 EchoLLM |

## 目录结构

```text
.
├─ config/                 # Django 工程配置（settings 按环境拆分）
├─ apps/                   # 业务应用（每个 app 自带 models/api/tests/migrations）
│  ├─ accounts/            # 账号与患者档案（长期记忆事实）
│  ├─ consultations/       # 问诊会话、消息、WebSocket
│  ├─ agents/              # Agent 运行记录与步骤（监控/计费数据源）
│  ├─ rag/                 # 知识库文档、切片、索引任务、检索 API
│  ├─ billing/             # 价格表、用量流水、每日预算
│  ├─ monitoring/          # 指标与失败事件
│  └─ common/              # 分页、统一异常、健康检查
├─ agents/                 # 多智能体框架（与 Django 解耦，可单独测试）
│  ├─ base/                # BaseAgent / Coordinator / Registry / LLM 抽象
│  ├─ specialists/         # 7 个专职 Agent
│  ├─ debate/              # 辩论编排（LangGraph 接口）
│  └─ prompts/             # 各 Agent 的 system prompt（版本化文本）
├─ rag/                    # 检索工程（去重 / 切片 / 评估 / 重排协议）
├─ frontend/               # Vue3 前端
├─ infra/                  # Dockerfile、compose、nginx
├─ docs/                   # 架构、ADR、运行手册、OpenAPI、需求文档
├─ scripts/                # 初始化 / 开发脚本
└─ tests/                  # 跨模块测试（unit / integration / e2e）
```

## 快速开始（Windows）

```powershell
# 1. 初始化虚拟环境 + 依赖 + 数据库 + .env
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1

# 2. 启动后端（http://127.0.0.1:8000）
.\.venv\Scripts\python.exe manage.py runserver

# 3. 启动前端（http://127.0.0.1:5173）
cd frontend
npm install
npm run dev
```

验证：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## 环境变量

复制 `.env.example` 为 `.env` 后填写。**`.env` 不入库**。

| 变量 | 说明 |
| --- | --- |
| `DJANGO_SECRET_KEY` / `DJANGO_DEBUG` | 生产必须换密钥并关闭 DEBUG |
| `POSTGRES_*` | 配了 `POSTGRES_HOST` 就走 PostgreSQL，否则 SQLite |
| `REDIS_URL` / `CELERY_*` | 缓存、频道层、任务队列 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 任意 OpenAI 兼容服务；缺 Key 时走离线占位 |
| `ENABLE_DEBATE` / `ENABLE_SAFETY_GATE` | 演示时逐项开关创新点 |
| `DAILY_TOKEN_BUDGET_PER_USER` | 每用户每日 token 预算 |

## 协作流程

```text
用户消息
  → triage（红旗征 / 追问）
  → retrieval（证据 + 引用）
  → risk ∥ medication（并行）
  → debate（可选，分歧收敛）
  → explainer（SOAP + 白话）
  → safety（合规拦截 + 免责声明）
  → 回复（带 citations 与 trace_id）
```

每次运行都会写 `AgentRun` 与 `AgentStep`，监控面板与计费从这两张表取数。

## 开发约定

- 一个需求 = 一个 `apps/<domain>/services/` 函数 + 一个 API + 一组测试；
- 任何跨模块能力先定义协议（Protocol），再接实现（便于替换 Milvus / LLM）；
- 提交前：`ruff check .`、`pytest -q`、`pre-commit install`；
- 配置只从环境变量读，不在代码里写死密钥或连接串。

## 路线图

| 阶段 | 内容 |
| --- | --- |
| P1 | 骨架跑通：协调器 + 7 Agent + 问诊 API + 前端页面 |
| P2 | Milvus 全量索引 + 混合检索 + hash 去重 + RAG 评估 + LoRA 微调实验 |
| P3 | 白话解释打磨 + LangGraph 辩论 + 数据飞轮 |
| P4 | Redis 缓存 / 计费 / LangChain 历史对话 / 调用链与监控面板 |

## License

MIT，见 [LICENSE](LICENSE)。