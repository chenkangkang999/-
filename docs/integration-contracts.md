# 双人接口契约 v1

## 所有权

本次负责：explainer、safety、debate/LangGraph；LLM网关；Django/Vue、鉴权、发布控制、计费、监控、部署。
同学负责：Coordinator、triage/retrieval/risk/medication；RAG/Milvus/LoRA/评测；LangChain历史、检索缓存与数据工程。
不改同学四基础Agent的业务代码。界面数量来自注册表，debate为现有兼容入口。

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
数据工程从Feedback读取；未经授权不自动用于训练。

## 配置与失败

价格、金额预算和模型配置必需真实提供。PRICE_NOT_CONFIGURED、BUDGET_NOT_CONFIGURED、BUDGET_EXCEEDED、TIMEOUT、RATE_LIMITED、INVALID_OUTPUT及未接入都不伪装成功。
本地SQLite/进程内频道为明确开发模式，测试provider只存在tests/。
