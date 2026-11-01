# 训练数据、日志和反馈飞轮

此模块在 Web 层连接同学的 BGE-M3 训练脚本；不会在收到评价时自动运行 GPU 或替换检索模型。当前 `scripts/training.yaml` 仍保持线性基线，历史余弦实验采用自己的配置快照。

## 数据与产物来源

`configs/learning_manifest.yaml` 是文档资产与实验报告的声明，所有条目明确标记 `document_reported`；声明的行数不是本机核验值。`python manage.py sync_learning` 只从配置允许目录核验文件行数、字节和 SHA-256，并读取训练状态及评测 CSV。没有文件时为 missing，读取错误时为 error，不填模拟日志或进度。

参数见 `.env.example` 的 `LEARNING_*`。训练配置、数据目录、产物目录、交接目录都可配置；API 不接受任意文件路径。训练目录中的 `trainer_state.json`、`training_run.json`、`training_events.jsonl` 和固定评测 CSV 被有界导入，事件去重、分页。只有标准 TrainerState 时状态为 unknown，不能据 checkpoint 猜测进程仍在运行。过期 running 观察也会变为 unknown。

页面 GET 只读取配置和数据库，不初始化或更新清单。首次空库返回空列表，overview 的 `sync_required=true`，由管理员显式 POST sync 或 CLI 初始化；避免概览、资产、评测并发请求竞争 SQLite 写锁。

staff 可通过 `datasets/<key>/preview/?limit=3` 查看受限样例，默认最多5条、配置上限10条；仅支持资产已绑定的允许目录内 JSONL/CSV，流式读取有限行并限制行/字段长度，遮盖常见手机号、邮件和证件号。文件大小或修改签名变化返回409，缺失返回404，超限返回413，限流返回429；需重新同步核验。预览始终 `Cache-Control: no-store`，不下发全量数据，自动遮盖仍需人工复核。

`python scripts/learning_export.py --run-dir <运行目录> --output <交接ZIP>` 导出观测 JSON/JSONL/CSV；不包含权重、样本或 pickle。接收方把允许的文件放入 `LEARNING_ARTIFACT_ROOT` 或 `LEARNING_HANDOFF_ROOT` 后同步。含训练集与 adapter 的历史包可用 `scripts/learning_import_bundle.py` 安全导入：仅提取允许的 JSON/JSONL/CSV/safetensors，拒绝穿越和符号链接，限制大小，不覆盖不同内容。`.pt/.pth/.bin` 不提取、不加载。

历史早停需要显式 `--confirmed-early-stop --historical-config <配置快照>`，不能仅凭 global_step 小于 max_steps 认定早停。进度是实际 global_step/max_steps，例如 1200/2500 仍为 48%，早停状态不会补成100%。事件时间是导入时间，历史没有起止时间时保留空值。

### 本轮实际导入

用户提供的历史 ZIP SHA-256：`20d2e1287b0bb13fc319d7abc569d7cec1d00657d17bf786e36c4ee3a860e1e2`。

- cMedQA2 训练文件核验 90,000 行、69,184,630 字节；验证文件 10,000 行、7,673,723 字节。数据和模型在 Git 忽略目录，未入库。
- 余弦历史 checkpoint-1200：global_step 1200 / max_steps 2500，epoch 0.96，36 条 log_history；用户确认此轮触发早停。历史配置是 cosine / wd=0.01 / 2 epochs，与当前线性选型分开。
- 实际日志 best_metric 为 0.2044462562，best checkpoint 指向缺失的 checkpoint-900；末次 eval_loss 为 0.2069094032。文档中的最低 loss 描述与产物不一致，以实际产物展示。
- 三组 CSV 有 7 项真实文件指标，但缺少模型指纹清单；不能证明其 cosine 列对应本包 checkpoint-1200。该 adapter 只登记为未验证候选，不启用，也不冒充遗失的线性 adapter。
- 评测是单查询 1 正例 + 19 负例的候选池，不是 Milvus 全库 Recall。未提供 DDInter、ICD/NMPA 与 Framingham 文件仍显示 missing。

## 反馈转为检索训练数据

1. 用户在原反馈 API 显式传 `training_consent: true`；默认 false。可再次提交 false 撤回，刷新后仍展示服务器保存的授权状态。重复相同反馈不会改变版本或使既有标注失效。
2. 同意的成功回复进入 pending 候选。手机号、邮箱、身份证号自动替换；姓名、住址等仍需人工确认脱敏。用户评价不是文档相关性真值，👎不会直接变负样本。
3. 管理员标注 query 对应的相关/不相关**来源证据**，填写来源与审校理由，确认脱敏和证据；拒绝直接使用整段 LLM 回复作为真值。正负证据相同或重复指纹会拒绝。
4. 审核通过后冻结批次。NFKC/大小写/空白归一化后的 query hash 作为分组单位，防同查询跨训练/保留验证集；检查既有验证集查询重叠。外部验证集缺失时显示 not_connected，默认禁止准备训练。
5. 可导出同学脚本使用的 `{query, positive, negative}` JSONL，或 FlagEmbedding 的 `{query, pos: [...], neg: [...]}`。批次记录来源、hash、授权版本和 train/validation 划分。撤回授权、反馈修改或重新标注后，旧批次下载与准备返回410。
6. prepare 写入独立数据/配置快照，显式 `data.use_explicit_negatives=true`，供 MNRL 消费人工难负例；不修改原训练 YAML。生成 GPU 主机命令，状态仅为 ready。新增任务记录不能作为已训练证据。

导出至外部的副本或已经训练的模型无法通过撤回自动删除；需联系训练负责人按 manifest 追溯处理。Web 会阻止未来导出和准备。

## 真实训练与观测

显式运行 prepare 返回的 `scripts/learning_run.py` 命令。wrapper 使用同一 GPU Python 调用现有 `train_lora.py`，不安装依赖、不改 PyTorch，不改变原优化器参数；可选观测 callback 保存真实 TrainerState。不会把嵌套 eval TQDM 的 n/n 当成训练进度。正常结束、失败、中断均写结构化状态；进度只来自真实状态。

`--with-eval` 随后调用现有评测脚本，生成包含 CSV 与 adapter 指纹的 `evaluation_manifest.json`。不启动的训练不产生完成事件；stdout 不作为公开日志，Web 只展示指标和受控操作事件。

## 模型版本与人工启用

`learning/models/` 返回候选、活动版本和启用日志。登记要求真实 LoRA config/safetensors 边界与 SHA 核验、关联运行及实际 CSV。没有匹配该 adapter 指纹的评测清单时仍为 unverified，禁止启用；旧 CSV 或文档表不够。

人工启用需 `evidence_confirmed=true` 和理由，校验产物未变，写不可变更的切换记录。回滚指向记录中的前一版本；首次启用可恢复“无登记活动 adapter”的原配置路径。检索实现通过 `apps.learning.registry.active_adapter()` 端口使用活动版本，训练完成不会自动热替换。

## API 与权限

所有 `/api/v1/learning/` 端点要求 staff Session，写入保留 CSRF。列表返回 `{results: [...]}`。主要资源为 `overview/`、`datasets/`、`sync/`、`runs/`、`runs/<uuid>/events/?after=<cursor>`、`evaluations/`、`models/` 和 `flywheel/{overview,collect,candidates,batches}/`。审校、导出、prepare、register/activate/rollback 的请求字段与前端类型一致。普通用户仅能在自己的会话提交和撤回反馈授权，不能读取全体候选或训练数据。
