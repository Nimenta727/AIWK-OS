# 2026-11-21 01:25 — Optional guest-only local LLM proposal gateway / AIWS 内置小模型接口

## 修改
- 新增 os/runtime/aiws_local_model.py：可选 llama.cpp OpenAI-style JSON 输出适配；只调用客户机 127.0.0.1:18080，禁用代理，不允许选择云/主机 URL，默认关闭。
- 模型只能返回 read-only 工具计划，必须通过 catalog/schema/相对 guest 路径严格校验；不得直接执行、不允许文件写入、shell、提权、guest/host 内核或 hypervisor 调用，所有提案均标记 requiresReview/executed=False。
- 新增 os/verify/test_local_model.py，使用内存中模拟 loopback llama server 测试正常提案、禁用时不访问服务、拒绝 host/shell/kernel/write 的越界输出和伪装指令。
- 同时修复 aiws_tasks.py 中阶段数据库记录顺序应按 ordinal（计划原始顺序）而不是相同时间戳下的随机 UUID 排列，保证 DAG UI 输出稳定。
- 文件：os/runtime/aiws_local_model.py, os/runtime/aiws_tasks.py, os/verify/test_local_model.py, 本 routine。

## 完成度
模型本体尚未下载/加载，训练权重/微调尚未实施。本次只是经测试的可替换提议接口和拒绝越权逻辑。GPU 3–5GB 指标未验证，也不承诺所有 2B 模型在相同显存运行。运行端必须安装在独立 guest 并使用普通用户权限；不得通过宿主 GPU/device passthrough 获取能力。

## 下一步
把本地模型建议接口连接 AIWS 工作台（用户明确点击才调用）及 guest DAG；建立可审计训练数据 / eval 套件 / opt-in QLoRA，验证模型版本与隔离；完成 OS GUI 与 NixOS 真实启动。
