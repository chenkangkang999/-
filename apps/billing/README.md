# 计费接入约定

Web 通过 `MeteredLLM(inner, user=..., consultation=..., trace_id=..., run_id=...)` 注入
`context.facts['_llm']`。保留 `complete(system_prompt, user_prompt, *, agent)` 签名及原始
`LLMResponse`，不将模型正文写入账单。

## 启用真实计费

1. 在 Django 管理后台新增 PricePlan，填写与请求一致的 `provider`、`model`、币种、
   input/output 每千 token 单价和生效时间。缓存输入有单独价格时填写
   `cached_input_per_1k`；留空按普通输入价格计算。价格依据应来自当前供应商定价。
2. 配置 `DAILY_COST_BUDGET_PER_USER` 为该币种下的正数；可同时配置
   `DAILY_TOKEN_BUDGET_PER_USER`。两者均包含未结束调用的预占。
3. HTTP 适配器的 `LLM_MAX_OUTPUT_TOKENS` 必须真正发送给服务商，不能只用于本地预估。

没有模型价格或有效预算配置会在外部调用之前失败，返回 `PRICE_NOT_CONFIGURED` 或
`BUDGET_NOT_CONFIGURED`，不会使用任何演示价格兜底。

## 账单口径

- 调用前按保守输入边界和最大输出额度预占；请求成功后按真实 input/output usage
  结算，保存调用时的单价快照。更新价格不影响历史账单。
- 缺失 usage 时，按预占边界保守估算并标记 `measurement=estimated`；该金额不是供应商
  的精确账单。历史未核验的旧记录标记 `legacy`。
- 明确被拒绝的 429/4xx 或未发送请求的普通错误释放预占。`TIMEOUT`、
  `LLM_CONNECTION_ERROR`、`LLM_PROVIDER_UNAVAILABLE`、`INVALID_PROVIDER_RESPONSE`
  无法确认是否已被供应商计费，因此保留预占并记录故障；故障记录保存 reservation call_id，
  供维护者核对供应商账单。核对确认未收费后才调用 `release(call_id)`，收费则补齐结算。
- 实际 usage 超出预占时仍保存真实消费，记录故障并阻止继续生成本次回答；这不能代替
  供应商账户级限额。
- 结算失败时保留预占以防继续超支；不自动删除尚未核对的预占记录。
- 进程在预占后退出也可能留下预占。当前未实现自动过期或供应商对账任务；应先按
  call_id 核对供应商账单，再由维护者调用 `release(call_id)` 或补齐结算。自动释放
  未核对记录会重新开放可能已经消耗的额度，因此本实现保持保守阻止继续消费。

账单汇总 API 的 `by_query` 为兼容现有前端保留按 `consultation_id` 汇总的会话口径；
**逐查询口径使用 `by_run`**，按 `run_id + consultation_id` 分组，包含一轮查询中全部
Agent 调用的 token 与费用。没有 run_id 的历史记录仍计入总账及会话汇总，不混入
逐查询结果。`latest` 列出每次模型调用，并提供其 run_id 以便溯源。

跨模块直接上报真实用量可调用 `record_usage(..., call_id=稳定UUID)`；不要同时使用
该函数和 MeteredLLM 对同一次调用重复记账。

## 监控接口

同学可通过 `apps.monitoring.services.record_metric` 写入 `retrieval.latency_ms` 和
`retrieval.hit_count`。必须传入可信的 user、trace_id；重试时复用 event_id。
没有采集结果时监控 API 返回 `not_connected` 和 null，不用零值冒充已完成集成。
