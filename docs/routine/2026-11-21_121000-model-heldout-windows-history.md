# 2026-11-21 12:10 — 本地模型真实 QEMU 独立评测及 Windows→Linux Agent 历史证据投影

## 完成的改动 / Changes

1. **明确拒绝协议**：LocalPlanner 将越权/宿主/任意系统写入请求转换为经过校验的 tool=refuse/arguments={}。拒绝是不可执行的终止状态；Linux Agent service 也独立阻止拒绝进入 DAG。React 工作台展示拒绝原因，不提供复制为可执行任务。
2. **冻结独立评测集与指标**：os/model/ci/heldout_v1.jsonl 提供 26 条双语合成 held-out 用例（14 safe + 12 unauthorized），与 training/development 语句不重叠。guest_benchmark.py 统计严格工具准确率、工具+参数完全匹配率、明确越权拒绝率、schema 有效率、p50/p95/max 推理时间、真实 llama-server 进程 VmRSS/VmHWM、失败类型。invalid JSON 和 schema 失败不冒充模型拒绝。
3. **真实客户机推理链路**：升级 guest_inference_smoke.py，在一次性 QEMU 客体内启动固定 guest systemd 用户模型服务，从相同 LocalPlanner 连续推理独立集合；读取真实进程 RSS，打印可机器解析的 smoke/sha 回执。aiws-boot-smoke 将输出从 root-owned FD 重定向到 ttyS0，构建脚本仅在 CI-model ISO 中安装 held-out 资料；GitHub Actions 从串口提取并上传 metrics JSON，绝不上传权重或原始 prompt。
4. **Windows 迁移**：在原 WorkTask 只读导入上增加 PlanRevision（ID、SHA、时间、路径哈希）、UnifiedWorkItem、AgentRun（Evidence、开始/结束、adapter 哈希）、ExecutionRecord（事件/归因/时间/metadata 哈希）和 workflow stage 的 unmapped 投影，仍保留零执行权限、同一个 SQLite store、审计摘要和跨重启读取校验。
5. **回归与交付标准**：增加模型评测集/指标测试、明确拒绝测试、Windows 完整投影/敏感值不落盘/跨重启不可执行测试；升级开发训练数据中的越权金标；新增外部微调标准和 Windows→Linux 迁移映射规范并更新 README / 文档索引。

## 影响文件 / Files affected

- 模型服务与 Linux Agent：os/runtime/aiws_local_model.py、aiws_workbench.py、aiws_agent_service.py、aiws_windows_compat.py。
- guest ISO 与 CI：os/debian/build.sh、os/debian/config/includes.chroot/usr/local/bin/aiws-boot-smoke、os/model/ci/guest_benchmark.py、heldout_v1.jsonl、guest_inference_smoke.py、.github/workflows/aiws-real-model.yml。
- 模型/UI/测试：os/model/training/synthetic_intents.jsonl、os/model/training/train_lora.py、os/verify/test_model_benchmark.py、os/verify/test_local_model_dataset.py、os/verify/test_local_model.py、os/verify/test_windows_compat.py、desktop/AIWorkstation.Frontend/src/os/GuestTaskStudio.tsx。
- 文档：docs/AIWS_MODEL_FINETUNING_STANDARD.md、docs/AIWS_WINDOWS_TO_LINUX_AGENT_MAPPING.md、docs/AIWS_LOCAL_MODEL.md、docs/README.md、os/README.md、README.md、docs/routine/README.md、本文件。

## 验证 / Verification and honest status

- **可确认的代码事实**：独立评测输入是 synthetic JSONL，模型建议仍不执行；旧 Windows 历史阶段仍以 windows.unmapped 进入 Linux SQLite，拒绝审批/调度。
- **提交时尚未验证的结果**：Python/React/ISO/QEMU CI 尚未完成；因此没有声称实际 2B 推理准确率、越权拒绝率、p95、peak RSS 已达标。CI run 需根据提交 SHA 另行核验，失败或未运行均为 NOT VERIFIED。
- 正式发布仍需 ≥200 个独立测试案例与风险覆盖；26 例仅供 CI smoke。模拟测试通过并不能替代真实 GGUF/llama.cpp/QEMU 推理与人工安全验收。

## 已知问题 / Known gaps

- QEMU TCG 2 vCPU 推理可能触发 120 秒 timeout/CI 运行上限；不得修改测试集、放宽门槛或伪造 metrics 把失败说成成功。
- Windows 历史导入 API 仍是单任务小型 JSON，UI 的完整 plan/run/event 时间轴和新 Linux tool mapping 尚未实现，必须逐项审阅后独立审批。
- 客户机 root 可能篡改整个 SQLite 和 audit chain；没有正式权限 broker、持久固件恢复证明，也没有默认分发的微调后模型。

## 下一步 / Next steps

1. 检查该提交对应 Python static、React frontend build、model CPU/QEMU job、常规 QEMU GUI 的真实日志、状态和 artifact；逐项修复失败后另写独立 docs/routine 时间记录。
2. 若真实模型 smoke 成功，保留 pinned GGUF/model/server SHA、dataset SHA、分组准确率/越权拒绝率、p50/p95/peak RSS 和串口证据；若失败，按失败分类改 prompt 或训练 development 样本，**不得利用 locked test 调参**。
3. 建立正式 ≥200 条独立许可审查集，邀请外部贡献者按 docs/AIWS_MODEL_FINETUNING_STANDARD.md 提交 LoRA/QLoRA reproducibility manifest，经过质量+安全双重 review 才考虑默认集成。
4. 在 QEMU GUI 中展示 Windows 计划/运行/阶段事件时间轴；设计明确 Tool Mapping → 新 Linux task → 人工审批 → 受界执行 → 审计回滚的后续流程。
