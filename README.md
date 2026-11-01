# 医疗问诊多智能体协作系统

Django 5.2 / DRF / Channels + Vue 3 / TypeScript / Pinia / Element Plus / ECharts。
本分支补齐 LLM 工程与 Web 平台；同学的算法、基础Agent与数据工程通过接口接入。
用于答辩与工程演示，输出不替代医师，不自动开具处方。

## 当前分工和完成边界

- 本次：真实白话解释、安全双判、LangGraph辩论；登录/CSRF、问诊历史、异步任务、审核后回复、WebSocket、证据、反馈、Agent测试、计费与监控。
- 同学：Coordinator和triage/retrieval/risk/medication、RAG/Milvus/LoRA、检索评测、LangChain历史。
- 保留同学的既有骨架业务；未完成能力显示未接入/数据不足。未提供校准数据不生成诊断概率，没有真实实验不显示LoRA提升。
- 测试provider只在tests/，本分支生产路径不自动使用Echo。旧base/LLM入口属于保留兼容代码；新增模块统一使用注入网关。

接口、字段和事件见 [双人接口契约](docs/integration-contracts.md)，验收记录见 [本地验收](docs/acceptance.md)。

2026-11-01 页面改版与复查见 [改版说明](docs/ui-refresh-2026-11-01.md)，远程两条检查的结论见 [CI 诊断](docs/ci-review-2026-11-01.md)，背景提示词与素材记录见 [素材来源](docs/assets/medical-background.md)。用户审阅后已授权提交，提交范围、独立 CI 修复与复验记录见 [交付备注](docs/releases/2026-11-01.md)。

## 本机运行

需要 Python 3.12、Node.js 20+；无需为Web重新安装GPU PyTorch。
原GPU训练环境保持原样，Web可用独立虚拟环境，不安装AI训练依赖。

1. 执行 scripts/bootstrap.ps1（可传 -Python 指定解释器），或手动创建venv、安装 requirements/dev.txt 并执行 python manage.py migrate。
2. 复制 .env.example 为 .env；APP_RUNTIME=local、POSTGRES_HOST留空时使用SQLite+进程内频道+线程执行器。
3. 填写真实 LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / LLM_API_KEY；填写 DAILY_COST_BUDGET_PER_USER。
4. 执行 python manage.py createsuperuser。在 /admin/ 创建匹配provider/model的PricePlan，设置输入/输出每千token单价、币种、生效时间；缓存价格可选。无匹配价格或预算时拒绝外呼，不虚构费用。
5. 后端：python manage.py runserver 127.0.0.1:8000 --noreload。
6. 前端：cd frontend；npm ci；npm run dev。打开 http://127.0.0.1:5173，用已创建账号登录。
7. 改动.env后重启后端。普通用户通过管理后台创建；Agent独立测试只对staff开放。

本地线程模式仅适用于单进程开发。进程重启可能中断在途任务；生产使用Celery，详见运行手册。
scripts/seed_demo.py现仅接受显式用户名并交互输入密码，不再创建固定密码、虚构医学文档或写死价格。

## 配置表

所有配置在.env.example登记；.env和患者数据禁止入库。
| 配置 | 用途 |
|---|---|
| DJANGO_SETTINGS_MODULE / DJANGO_SECRET_KEY / DJANGO_DEBUG / DJANGO_ALLOWED_HOSTS | 环境、密钥与允许主机 |
| APP_RUNTIME / CONSULTATION_EXECUTOR / CONSULTATION_WORKERS | local单进程或services；thread/inline/celery与并发数 |
| POSTGRES_* / REDIS_URL / CELERY_* | 数据库、频道、任务队列，开发可不用外部服务 |
| LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / LLM_API_KEY | 真实供应商与模型配置 |
| LLM_TIMEOUT_SECONDS / LLM_MAX_RETRIES / LLM_TEMPERATURE / LLM_MAX_OUTPUT_TOKENS / LLM_REQUEST_OPTIONS | 外呼限制、生成参数和供应商可选JSON参数 |
| LLM_PROMPTS_DIR / SAFETY_RULES_PATH / DEBATE_MAX_ROUNDS | 提示词、规则版本与辩论轮次 |
| ENABLE_DEBATE / ENABLE_SAFETY_GATE | 辩论开关；Web发布护栏始终强制，不能通过开关绕过 |
| ANSWER_CHUNK_SIZE | 审核后传输分块大小 |
| COORDINATOR_PROVIDER / HISTORY_PROVIDER / HISTORY_MESSAGE_LIMIT | 同学的协调器与历史适配器 |
| MILVUS_URI / MILVUS_COLLECTION | 同学检索服务配置 |
| DAILY_COST_BUDGET_PER_USER / DAILY_TOKEN_BUDGET_PER_USER | 每用户每日金额/Token额度 |
| BILLING_CURRENCY / BILLING_INPUT_TOKEN_OVERHEAD / BILLING_ESTIMATOR_ENCODING | 币种和预算预估配置 |
| MINIO_ROOT_USER / MINIO_ROOT_PASSWORD | 可选RAG容器凭据 |
| frontend/.env.example | API、WebSocket与开发代理配置 |

价格存数据库且调用时保存快照。实际结算优先供应商usage；tiktoken仅作预估。
LLM_MAX_RETRIES仅用于429明确拒绝；超时、断连和5xx不自动重试，未知费用保留预算预占，核对供应商账单后再处理。
缺失usage的记录明确为estimated；账单不是供应商充值或支付系统。
深度模型内部推理、未经审核候选回复均不通过公开API或事件暴露。

## 验证

python -m pytest -q
python -m ruff check .
python manage.py makemigrations --check --dry-run --settings=config.settings.test
前端：npm run test；npm run build。

真实API联调需要配置密钥、价格、预算；不会在CI调用付费服务。
请区分：隔离测试通过、真实模型联调通过、同学算法联调通过、容器部署通过。

## Compose

根目录执行 docker compose --env-file .env up --build。
先填写POSTGRES_PASSWORD；Compose明确切换到services、Redis和Celery，覆盖容器连接地址。
RAG服务为可选profile：docker compose --env-file .env --profile rag up --build；
启用前填写MinIO账号密码，实际索引由同学提供。
默认Compose用于本机集成；公网部署必须使用生产settings、HTTPS、明确主机及安全凭据。
.dockerignore排除.env、数据库、患者数据、模型和虚拟环境，镜像不打包本机密钥。
