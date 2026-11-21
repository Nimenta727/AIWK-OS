# 2026-11-21 12:21 — 2B 本地模型与独立 Linux Agent 的受界系统上下文联动

## 修改
- `os/runtime/aiws_local_model.py` 增加最多 **2KiB** 的 guest-only 环境摘要，最多 24 个相对客户机文件名和 8 个近期任务（仅 ID、标题）；拒绝绝对路径、上跳、异常字段/控制字符、大块上下文。
- 将摘要标记为 `UNTRUSTED GUEST DATA`，仅作为本地 llama.cpp 单次推理中的背景数据，模型输出仍只能是经严格 schema 验证的只读工具提议；**不读取文件正文、不发送凭据、不访问云端或宿主**。
- `os/runtime/aiws_workbench.py` 从同 UID 独立 Agent 的 Unix IPC 获取 `workspace.tree` 和 `task.list`，形成简短系统视图；无模型时不采集上下文，Agent 不可用时使用空上下文而不是越权重试。
- 模型只允许用户主动点击建议/待审核计划，绝不直接执行；保留 CSRF、Host、Origin、任务 DAG、审批及审计独立校验。
- `test_local_model.py` 与 `test_workbench.py` 增加本地模拟推理、JSON context、越权路径拒绝、低预算和不泄露源文件正文的回归测试。
- 修改：model, workbench, two tests, routine README 和本日志。

## 结果与限制
- 静态/单元测试需要本提交 GitHub CI 实际成功后才能宣称通过；2B 真实模型 CPU 和 QEMU 工作流仍独立运行。
- 当前数据摘要仅包括文件名、任务标题、IDs；不等于完整 GUI 屏幕识别、系统内核权限或自主执行能力。上下文中不应放入用户未授权训练集，LoRA 训练仍是独立、显式开启流程。
- 本地 llama-server 不可以访问宿主 GPU，CPU-only、127.0.0.1 和权限限制保持不变。

## 下一步
- 真实 model-inclusive QEMU 验证含上下文的中文工具提议 JSON 正确率。
- 建立输入上下文大小、推理时延、RSS 与错误拒绝率的独立 held-out 指标。
- 对 Windows 兼容导入继续测试历史数据映射，并在客体 GUI 执行人工验收。
