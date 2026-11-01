# 同学训练提交的 CI 报错

本轮通过GitHub Actions实际日志核对4条提交：

| 提交 | 运行 | 结果 |
|---|---|---|
| c5fe06a | [41290524852](https://github.com/chenkangkang999/doctor-quest/actions/runs/41290524852) | 前端成功，后端Ruff失败 |
| 099f81f | [41286786410](https://github.com/chenkangkang999/doctor-quest/actions/runs/41286786410) | 前端成功，后端Ruff失败 |
| 9dd49ad | [41281145725](https://github.com/chenkangkang999/doctor-quest/actions/runs/41281145725) | 前端成功，后端Ruff失败 |
| 5c151a7 | [41274672145](https://github.com/chenkangkang999/doctor-quest/actions/runs/41274672145) | 前端成功，后端Ruff失败 |

日志共13项：UP009×4、UP015×5、I001×1、C420×2、E741×1，分布于download_model/train_lora/eval_retrieval/eval_retrieval_compare四脚本。原流水线在lint阶段退出，不能从这些红叉得出GPU训练失败的结论。

已在本地修复编码声明/导入/计数器/变量名等lint问题，没有通过关闭检查解决。默认线性调度、wd0、1epoch、关闭早停，以及原batch/LoRA/学习率参数保持不变。评测比较路径和标签改为配置；新增观测回调默认关闭、显式难负例默认关闭，飞轮准备的新配置才显式启用。

原训练Dataset只消费query/positive；飞轮新增的query/positive/negative通过显式开关被MNRL Dataset真正消费，不能仅导出三元组就称难负例已生效。三组CSV的20候选池评估与全量RAG监控分开显示。

诊断阶段没有数据，后来用户另行提供ZIP，已核验90,000训练/10,000验证、余弦36条日志、checkpoint-1200和真实评测CSV。实际导入结果见[训练操作](learning-operations.md)，与GitHub跟踪文件是否包含数据是两回事。

本地全量检查见[本轮验收](acceptance-v2.md)。本轮先完成本地审阅，再按用户授权直接提交main；原来的GitHub红叉仍是旧提交结果，新提交CI独立确认。发布范围与边界见[v2发布备注](releases/2026-11-01-v2.md)。
