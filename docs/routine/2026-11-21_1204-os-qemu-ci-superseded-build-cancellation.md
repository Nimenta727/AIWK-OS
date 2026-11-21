# 2026-11-21 12:04 — 同分支 ISO/QEMU 仅验最新提交，降低 CI 重复构建开销

## 修改
- GitHub Actions `.github/workflows/aiws-os-image-boot.yml` 增加 concurrency 组（workflow + ref）。
- 对连续 push 的 OS 自动验收启用 `cancel-in-progress`；同分支的旧提交构建可以被取消，以减少重复下载 Debian 包、构建 ISO、分配 QEMU 软件模拟 CPU 的计算耗费。
- `workflow_dispatch` 手动专项运行自身不主动取消旧任务，适合需要保留专项诊断证据的验收。
- 本次改动**只针对 OS ISO/QEMU 工作流**，不修改正在运行的独立 Qwen3.5-2B CPU/guest model 验收，避免丢失真实模型数据。
- 修改文件：上述 workflow、本日志及 `docs/routine/README.md`。

## 验证与限制
- GitHub Actions 的取消行为取决于平台调度及运行时机，不能认为已经完成的旧工作流已被删除。新的 AIWS OS 镜像、QEMU UI、Agent、Windows 工作流导入验收仍需看最新完整跑完的运行结果。
- 节省的是 CI runner 与 ISO 构建资源，**不等于模型推理 Token**；AIWS 小模型的 tokens 由本地 llama.cpp 消耗，云端请求仍为 0。
- 该并发策略只处理同一 repo/ref/workflow，其他分支不受影响，独立云端模型不会接触 guest 主机或 host 权限。

## 下一步
- 核对仅最新提交完成 ISO/QEMU 端到端截图、GUI click、Windows import、独立 Agent 生命周期。
- 阅读 CPU 2B 真实推理的独立指标与后续 model-inclusive QEMU 审计证据。
- 将 Win/Lin DAG 兼容性中尚未映射的阶段审查/映射流程完善并复核。
