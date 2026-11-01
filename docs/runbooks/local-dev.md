# 本机运行与真实联调

## 项目启动
按根README安装Python依赖和前端依赖、迁移数据库，并创建管理员。
默认本机使用SQLite+进程内频道+线程执行，必须保持单进程；使用--noreload避免刷新代码打断在途任务。
python manage.py runserver 127.0.0.1:8000 --noreload
frontend内执行 npm run dev。

## 模型连接
运行 python scripts/configure_local.py 打开本地配置窗口。API Key只保存至.gitignore排除的.env。
用户本次选择：provider=deepseek，base_url=https://api.deepseek.com，model=deepseek-v4-pro，CNY每日每用户额度2。
这些是本地配置，不是程序中的固定模型/价格/额度。交付源码包不含.env或密钥。

LLM_REQUEST_OPTIONS是可选JSON对象，供不同供应商配置thinking、response_format、reasoning_effort等。
例如DeepSeek可设 {"thinking":{"type":"disabled"},"response_format":{"type":"json_object"}}。
核心model/messages/stream/token上限不能被此对象覆盖。
修改.env后重启后端。模型调用参数全部从环境读取。

## 价格配置
PricePlan按provider、model、币种及生效时间查询。输入、输出及缓存输入的单位为每千token。
若官方价单位是每百万token，录入前除以1000。不要直接把每百万价格填入每千字段。
来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
2026-10-31本次联调用当日空闲时段Pro报价配置了本地PricePlan；价格可从管理后台修改。
供应商价格和时段可能变化，正式使用前核对并新增价格版本。历史UsageRecord使用调用时快照。
此项目账单按所配置价格计算；不是供应商充值、支付或自动对账服务。

## 同学接入
协调器：配置COORDINATOR_PROVIDER，保持run(text,context,enable_debate)。
历史：配置HISTORY_PROVIDER，实现HistoryPort；默认数据库历史不冒称LangChain。
所有付费Agent使用context.facts["_llm"]，否则无法统一预算。
检索埋点、反馈、风险及引用字段见docs/integration-contracts.md。

## 故障恢复
缺模型、价格或预算时明确失败，无自动Echo或伪造账单。
本地进程重启会中断在途线程；不自动重试以避免重复外呼。确认旧执行已结束后，由管理员核对运行状态。
供应商已响应但结算失败、或预占后进程退出时，可能保留reserved；先核对供应商账单，再按billing说明补结算或release。
外呼超时、断连、5xx或无效响应也保留预占，避免未知费用被重复消费；只有429明确拒绝可自动重试。
生产使用Redis+Celery。任务与价格需要运营方管理；当前没有供应商自动对账或本地线程持久队列。

## 验证边界
隔离测试、真实模型联调、同学算法联调、容器部署分别记录。不能将测试provider或未接入模块计为真实完成。
