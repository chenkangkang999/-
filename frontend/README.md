# 医协前端工作台

Vue 3 + TypeScript + Element Plus + ECharts。所有业务数据来自 Django API，无预置患者、模拟指标或演示账单。配置真实模型的密钥仅放后端。

## 本地运行

```powershell
npm ci
npm run dev
npm run test
npm run build
```

复制 `.env.example` 为 `.env.local` 可覆盖下列配置。后端需启动 ASGI 与异步 worker；账号由管理员创建。登录使用 Django Session + CSRF。

| 变量                 | 默认值                | 用途                               |
| -------------------- | --------------------- | ---------------------------------- |
| VITE_API_BASE_URL    | /api/v1               | 公开 API 基础路径                  |
| VITE_WS_BASE_URL     | 空                    | WS 服务根地址；留空从 API 地址推导 |
| VITE_API_TIMEOUT_MS  | 60000                 | HTTP 超时毫秒                      |
| VITE_RUN_POLL_MS     | 2000                  | 活跃任务状态恢复间隔毫秒           |
| DEV_API_PROXY_TARGET | http://127.0.0.1:8000 | 开发后端代理目标                   |
| DEV_HOST             | 127.0.0.1             | 开发服务监听地址                   |
| DEV_PORT             | 5173                  | 开发服务端口                       |
| VITE_WORKSPACE_BACKGROUND_URL | /images/medical-atmosphere-v2.webp | 工作台公开背景资源，可替换为自己的图片 |

`VITE_*` 会进入浏览器构建产物，严禁填写密钥。生产推荐同源反向代理 `/api`、`/ws`。生产修改 VITE 配置后需重新构建。跨域时后端还需配置 CORS、CSRF、Cookie 和 WebSocket Origin 白名单。

## 已接入行为

- 账号登录/退出、CSRF、受保护路由。
- 会话列表、历史恢复、异步运行、WebSocket 状态、安全回复、断线后轮询恢复、真实引用、SOAP、反馈。
- Agent 注册表、运行记录与管理员独立测试；只渲染后端实际返回的能力。
- 真实监控聚合和费用/预算/计量来源/流水；未接入项显示未接入或“—”。
- WebSocket 只消费后端发送的状态和审核后回复，不在前端推演医疗结论。
- 顶部导航、各页场景与流程入口集中于 `src/config/workspace.ts`；配色、卡片和布局通过 `src/styles/main.css` 的 CSS 变量统一。流程示意不是实时运行结果，所有状态与指标均来自 API。

## 验证

Vitest 覆盖证据链接协议过滤、SOAP、Agent进程、登录CSRF流程、权限隔离和错误提示。生产构建执行 TypeScript 检查。完整端到端验收还需真实后端、Redis、worker和用户自行配置的LLM。

## 训练展示与数据飞轮

新增 `/training` 与 `/flywheel`。两页只向项目管理员请求 `/api/v1/learning/` 数据；普通账号可以问诊、评价并管理自己的训练授权。

- 训练页读取资产核验、当前配置、持久化运行、增量日志与真实指标曲线。文档报告值和原始产物核验分开展示，历史余弦早停与当前线性选型分别记录，不把未执行步数补成 100%。
- `VITE_TRAINING_POLL_MS` 控制运行中的刷新间隔。按运行 ID 恢复，日志游标去重；离开页面停止刷新。同步本机产物不启动训练。
- 反馈的 `training_consent` 默认 false，可在刷新后恢复并撤回。授权不影响普通评价；赞踩不直接作为 BGE 正负例。
- 飞轮提供证据人工标注、脱敏确认、冻结批次、分组划分、JSONL 下载与训练配置准备。缺少模型或验证数据时展示后端错误，不假装已经训练。
- 真实模型与活动版本登记、回滚均有操作说明。当前只更新活动版本记录，在线 BGE 检索待同学接入，不自动切换。
- 问诊页按后端 `intake` 补充病史，`pipeline` 与真实 Agent 事件显示进度；工程协作示意不等同医生诊疗。

前端测试包括权限、报告与核验区分、日志游标、早停进度、证据审校、授权恢复/撤回、JSONL 格式及数据划分、模型活动登记确认与病史续接。业务接口仍由服务端进行最终校验。
