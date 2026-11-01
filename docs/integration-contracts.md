# 双人接口契约 v2

## 所有权

原分工为LLM/Web与同学算法模块分开；本轮用户追加授权补齐Coordinator、四基础Agent、RAG、LangChain历史与飞轮业务。同学继续提供真实数据和GPU训练/评测产物；这些模块仍按下面接口可替换，不强行重写同学训练超参。实际启用与实机验收边界见[需求覆盖](requirements-v2.md)。界面数量来自注册表，按业务流程排序。

## 保持兼容的入口

- BaseAgent._execute(context: AgentContext, message: AgentMessage) -> AgentResult。
- Coordinator.run(text, context, enable_debate=True) -> CoordinationResult。
- AgentResult: agent/content/citations/metadata/latency_ms/error。
- Citation: chunk_id/source/title/snippet/score。
- 配置 COORDINATOR_PROVIDER、HISTORY_PROVIDER 为同学适配器的Python导入路径。
- HistoryPort.load(consultation_id, before_message_id=...) -> [{role,content}]。默认读取数据库内已批准的历史，不宣称已实现LangChain。
- LLMClient.complete(system_prompt,user_prompt,*,agent) -> LLMResponse；使用 agents.llm 契约。Web将 MeteredLLM 注入 context.facts["_llm"]。
- 同学基础Agent调用付费模型时必须使用同一注入网关；绕过网关的外部消耗无法计入账单。

## 上游数据

context.record(agent,result.to_dict())保留既有约定，新增Agent从context.steps读取：
- triage.metadata：结构化主诉、症状、缺失信息；可增加diagnoses。没有校准来源时不生成诊断概率。
- retrieval.citations：真实chunk_id、来源、摘录；无命中为空列表，未接入/失败通过metadata/error明确标注。
- risk.metadata.risk_level：low/medium/high/critical；red_flags为真实识别结果。
- medication.metadata.contraindications/blocked_drugs：禁忌清单。
- 意见不足时辩论返回insufficient_input，不伪造争议。

## 新模块输出与发布

explainer.metadata：soap{subjective,objective,assessment,plan}、explanation、care_guidance、citation_ids。
safety.metadata：decision(pass/replace/block)、approved_text、severity、reasons、regulations、policy_version、reviewed_candidate_sha256、可选escalate。

Web只发布safety.approved_text。审核缺失、error、空正文或无效decision均失败关闭。旧Coordinator即使优先选explainer，发布层也不用该候选。
结构化SOAP仅在完整原解释通过审核时可见；被替换/拦截时不泄露原解释。

## 运行与事件

POST /api/v1/consultations/{id}/runs/
输入：{content,client_request_id:UUID}；新建202、幂等重试200。同ID不同输入或同会话已有活动任务时409。
GET /api/v1/consultations/{id}/runs/{run_id}/：状态、审核后的reply、steps、error及解释数据。
GET .../runs/：最近50次运行，用于刷新恢复。

WebSocket /ws/consultations/{id}/ 要求Session及会话所有权。
事件：{type,run_id,trace_id,timestamp,agent?,status?,payload}。
- agent.started/completed/failed：真实状态及耗时，无临床正文、内部推理。
- answer.chunk：审核后正文，payload.text为文本块。
- run.completed/run.failed：终态；客户端通过REST恢复最终状态。
- 基础Agent无开始钩子时不伪造running；同学可调用context.facts["_emit"](agent,"started")。
- 通知失败不影响持久化结果。开发线程模式仅单进程，服务模式用Redis+Celery。

保留POST .../messages/同步入口；成功201，失败503且reply=null。
状态：pending/running/succeeded/blocked/failed。活动任务和请求ID均有数据库唯一约束。

## 遥测与反馈

同学调用 apps.monitoring.services：
record_metric(name,value,*,user,trace_id,labels,event_id)，同event_id幂等。
检索名称 retrieval.latency_ms、retrieval.hit_count；labels不存症状/病史。
record_failure(code,*,source,user,trace_id,run_id)。

POST /api/v1/consultations/{id}/feedback/：
{run_id,rating:1|-1,comment?}，每用户每运行一条，可更新。
新增training_consent:boolean，默认false，支持撤回。数据工程从Feedback读取；未经授权不进入候选池，评分不自动等于BGE相关性标签。

## 配置与失败

价格、金额预算和模型配置必需真实提供。PRICE_NOT_CONFIGURED、BUDGET_NOT_CONFIGURED、BUDGET_EXCEEDED、TIMEOUT、RATE_LIMITED、INVALID_OUTPUT及未接入都不伪装成功。
本地SQLite/进程内频道为明确开发模式，测试provider只存在tests/。

## 本轮扩展契约

- `/api/v1/clinical/schema/`：动态输入字段与取值范围。创建运行可传`intake`；保留原content与client_request_id；同幂等键不同病史返回409。运行返回intake/pipeline，持久化恢复。
- `pipeline.updated`：payload.pipeline.stages含id/label/status/reason；状态pending/running/completed/waiting/skipped/failed。Agent事件payload.execution_status=skipped是明确跳过；事件不发送候选正文。
- `/api/v1/rag/status/`：管理员查看实际模式、可用索引、处理行数/全量标记、模型消费状态和临床来源状态；`/rag/search/`保留兼容结果，增加status/mode/degraded/error_code/index_version/model_version/cache_status/latency_ms。
- `/api/v1/learning/`：管理员资产、受限preview、显式sync、运行/事件、评测、模型版本与飞轮接口。全部路径、请求字段、权限和样例已补入[OpenAPI](api/openapi.yaml)。操作与文件约定见[训练文档](learning-operations.md)。
- 训练事件通过training_run.json/training_events.jsonl/trainer_state.json同步；GPU主机用learning_callbacks.py或learning_run.py生成真实事件，不猜测进程状态，不把tqdm评测步数作为训练进度。
- BGE三元组由人工确认相关/不相关来源并冻结；batch prepare生成独立配置，`data.use_explicit_negatives=true`才启用显式难负例。训练完成后仍需评测指纹绑定、人审登记、匹配版本全量建索引，不能直接从👍发布新模型。
