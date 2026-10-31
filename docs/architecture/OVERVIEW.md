# 架构总览

## 分层

```text
┌──────────────────────────── 前端 (Vue3) ────────────────────────────┐
│ 问诊页 · Agent 协作面板 · 监控面板 · 计费页                          │
└───────────────▲───────────────────────────────▲────────────────────┘
                │ REST / WebSocket              │
┌───────────────┴──────────── Django ───────────┴────────────────────┐
│ config/          设置、路由、ASGI、Celery                            │
│ apps/consultations  会话与消息（事实表）                             │
│ apps/agents         AgentRun / AgentStep（可观测性）                 │
│ apps/rag            文档 / 切片 / 索引任务 / 检索 API                │
│ apps/billing        价格 / 用量 / 预算                              │
│ apps/monitoring     指标 / 失败事件                                  │
└───────────────▲────────────────────────────────────────────────────┘
                │ 纯 Python 调用（不反向依赖 Django）
┌───────────────┴──────────── agents/ ───────────────────────────────┐
│ Coordinator → triage → retrieval → risk ∥ medication → debate        │
│              → explainer → safety                                    │
└───────────────▲────────────────────────────────────────────────────┘
                │
┌───────────────┴──────────── rag/ ──────────────────────────────────┐
│ dedup(hash) · chunker · embedding/retriever/reranker 协议 · 评估指标 │
└─────────────────────────────────────────────────────────────────────┘
```

## 三条边界

1. **`agents/` 不 import Django**：Agent 只依赖上下文与消息对象，便于单测和在脚本/离线评测中复用；
2. **Django 不写业务推理**：`apps/*/services/` 只做编排与持久化，推理逻辑留在 `agents/`；
3. **检索可替换**：`rag/retrieval/base.py` 定义 `Retriever` 协议，SQL 兜底与 Milvus 实现可互换。

## 关键数据流

1. `POST /api/v1/consultations/<id>/messages/` 写入用户消息；
2. `apps.consultations.services.coordinator` 构造 `AgentContext`（含患者过敏史等事实）；
3. `Coordinator.run()` 顺序 + 并行执行 7 个 Agent，产出 `steps` 与 `citations`；
4. 回复落 `Message`，运行记录落 `AgentRun`，会话风险级别更新；
5. 前端通过 REST 拉取结果，后续可订阅 `ws/consultations/<id>/` 接收 Agent 事件。

## 待办（P2/P3）

- Milvus 全量索引 + BGE-M3 + BM25 混合检索 + 重排；
- LangGraph 辩论图替换 `agents/debate/graph.py` 的占位实现；
- 引用归因校验与拒答阈值（创新点 I1/I2）落库与看板。