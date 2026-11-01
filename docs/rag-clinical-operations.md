# RAG 与基础 Agent 接入

## 本机已经运行的路径

`RAG_MODE=bm25` 使用真正的 SQLite FTS5 中文字符/双字词 BM25。显式公共语料清单在 `configs/rag_corpora.json`；当前读取用户提供、SHA已核验的 cMedQA2 训练文件 positive 文本，不将验证集或患者反馈直接混入知识库。

```powershell
python manage.py migrate
python manage.py sync_learning
python scripts/index_knowledge.py --limit 0
python scripts/import_clinical_data.py
```

`--limit 0` 是全部配置语料；非0运行会标为 limited，不能宣称全量。当前实际成功任务 #2 处理90,000行，61,987文档/切片、去重28,013；索引文件在忽略目录 `.local/rag`。重建会生成独立版本，失败不激活半成品。文件和切片hash基于NFKC归一化，保留来源hash与引用ID。

管理员在训练页查看 `/api/v1/rag/status/`，普通登录用户可调用 `/api/v1/rag/search/?q=咳嗽&top_k=5`。`hits`、`no_hits`、`not_connected`、`error` 是不同结果；索引缺失不能算“检索过但没有命中”。检索指标写入已有监控。社区问答作为研究语料，不能自动当成一线/二线用药指南。

## 切换真实 BGE + LoRA / Milvus

Web环境不需要安装torch；先在用户选定的、已确认GPU版torch的环境中安装 `requirements/rag.txt` 中其余依赖并检查依赖解析，保留原有torch。代码不会自动下载基座或在页面上安装依赖。

1. 提供完整 BGE-M3 本地基座、对应 tokenizer，以及通过指纹绑定评测的adapter。当前ZIP只有余弦checkpoint-1200，没有线性adapter或最优checkpoint-900。
2. 配置 `RAG_MODE=milvus`、`RAG_ENABLE_MODEL_LOAD=true`、`RAG_BASE_MODEL_PATH`、`RAG_ADAPTER_PATH`（或已核验活动模型登记）、`RAG_MILVUS_URI`、`RAG_DEVICE`、批量、超时、融合权重。
3. 执行全量 `index_knowledge.py --limit 0`。真实BGE向量写入独立Milvus collection，同时创建相同版本BM25；查询使用RRF融合，模型指纹与索引不一致则拒绝复用旧索引。
4. 若启用重排，配置 `RAG_RERANKER=cross_encoder` 和 `RAG_RERANK_MODEL_PATH`，提供完整本地Cross-encoder。缺模型直接返回未接入，不能把BM25分数称为重排分数。

RAG使用自有索引/检索代码，未用LangChain封装。LangChain只负责按会话加载已发布的历史消息。向量、LoRA加载与Milvus/Cross-encoder在本轮未进行实机验证。实测基座2.2GB下载预计约17–35分钟，因此遵照“很快才下载”未启动完整下载。

## 临床结构化输入与评分

问诊页面可展开“补充体征与慢病风险资料”；字段来自 `/api/v1/clinical/schema/` 和 `configs/clinical_fields.json`。基础病史5项为年龄、持续时间、过敏、现用药、慢病史；未知不自动转成“无”。20项可选字段包含体征、性别、妊娠/特殊人群、血脂及其单位等。不得把未勾选当作否认。

- NEWS2只在适用人群、Scale1所需完整信息齐全时给总分；部分体征只返回已观察预警，不补默认正常值。原版5–6分是Medium、7分及以上是High；平台四级风险标签另有映射说明。
- Framingham采用2008一般心血管病10年风险脂质公式、男女独立系数，30–74岁、无既往CVD、完整输入且明确mg/dL才计算；公式版本和SHA保存在配置，不把缺失数据填成“正常”。不是在缺失的4,240条数据上训练出的模型，也未经中国人群本地校准。
- ICD-10/ICD-11/SNOMED通过真实导入术语表精确映射；只有ICD-10文件时不能宣称完成ICD-11/SNOMED映射。`configs/triage.yaml`配置路径、允许编码系统和病种追问模板；术语CSV列为system/code/name/source，可附synonyms（竖线分隔）。

原始依据：[RCP NEWS2评分图](https://www.rcp.ac.uk/media/alxev00t/news2-chart-1_the-news-scoring-system_0_0.pdf)、[预警阈值](https://www.rcp.ac.uk/media/2acdezkd/news2-chart-2_news-thresholds-and-triggers_0.pdf)、[Framingham原始风险函数](https://www.framinghamheartstudy.org/fhs-for-researchers/fhs-risk-functions/cardiovascular-disease-10-year-risk/)。

## 用药数据的接入约定

`configs/clinical_evidence.yaml`配置文件位置与列映射，不将药名、相互作用和临床结论写死在代码中。将同学真实文件放入允许目录，然后显式运行导入命令；读取请求不写索引。源文件变更后状态为“待同步”，需要重建，不能继续拿旧表给肯定结论。

| 文件 | 默认列/结构 | 说明 |
|---|---|---|
| drugs/nmpa_domestic.csv、nmpa_import.csv | name、aliases、english_name | 中文/英文别名映射；原文件列名不同时改配置 |
| drugs/ddi_clean.csv | Drug_A、Drug_B、Level、Description | 无序药对去重、最高严重程度；无表是未接入，不是无相互作用 |
| clinical/reviewed_drug_evidence.json | JSON条目，包含drug_name、condition_terms、line、education、adverse_effects、source等 | 只接受guideline/drug_label来源及reviewed_by/reviewed_at；特殊人群与禁忌字段见导入器及测试 |

注册资料证明药名/注册事实，不自动证明治疗适应症；DDI与审校指南各自独立。未核实的社区回答不能进入处方逻辑。当前这些真实临床表尚缺，页面明确显示未接入；代码用测试临时数据验证业务分支。个体剂量、特殊人群剂量调整留给临床人员复核，正文不自动发布mg/片数等处方内容。

## 缓存、限流、容器

已审核科普回复缓存仅同一用户、全新会话、同一输入/患者上下文/政策/模型/知识版本可用；仅保存已发布正文。个体病史或多轮上下文不缓存，缓存变更/损坏/模型索引不匹配回到真实计费审核链。命中不新增LLM usage；本轮真实API已验证miss→hit且第二次0token。

本机local是单进程线程+LocMem+数据库session；服务模式是Redis缓存、Lua原子token bucket、cached_db会话、Channels和Celery。Redis限流不可用返回503，不静默取消限制。Compose显式选择Redis与Celery，两个应用容器共享runtime卷和只读data/models目录。若需向量依赖，设置`INSTALL_RAG=true`后重新构建，再从容器内显式建索引；不会将本机数据库/密钥/权重打进镜像。此轮未启动Docker全栈，不能把Compose静态校验等同部署成功。
