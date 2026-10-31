# ADR-0002：Agent 框架与 Django 解耦

- 状态：已接受
- 日期：2026-10-31

## 背景
多智能体逻辑需要在单测、离线评测、批处理中复用，不应依赖 ORM 或请求上下文。

## 决策
`agents/` 只依赖 `AgentContext` / `AgentMessage` 两个纯数据对象；需要检索时通过延迟 import 的适配函数接入。

## 后果
- 优点：`Coordinator` 可在无数据库环境下单测；换 Web 框架不影响 Agent。
- 代价：与 ORM 的交互集中在 `apps/*/services/`，需要保持这层薄。