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
