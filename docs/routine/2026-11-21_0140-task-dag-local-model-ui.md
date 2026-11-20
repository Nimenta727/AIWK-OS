# 2026-11-21 01:40 — Unified workbench persistent DAG and local small-model UI

## 改动
- 新增 desktop/AIWorkstation.Frontend/src/os/GuestTaskStudio.tsx，Linux AIWS 主窗口可创建阶段计划、依赖、保存任务、显示阶段执行结果、批准 guest 写操作，并查看 SQLite 保存的审计事件哈希。
- 新增本地小模型建议页：显示 guest-loopback 模型状态，用户主动提交简短操作意图，返回只读工具 JSON 建议，**默认不自动执行、不调用云端**。只有审阅后明确创建任务才会进入普通 DAG 调度。
- 在 OsWorkbench.tsx 与 CSS 中增加持久任务及本地 AI 导航，Windows WebView2 入口不受影响。
- 变更：GuestTaskStudio.tsx, OsWorkbench.tsx, OsWorkbench.css，本 routine。

## 测试、边界与不足
提交后需通过 native Windows Vite/TS 构建及 Linux ISO build/boot；当前 GUI 尚未做真正的 QEMU 用户点击/截图验收。模型 GGUF 权重及 llama-server 并未内置到 ISO；本地模型面板只在系统服务已显式配置时激活。阶段 UI 目前自动生成部分工具参数；复杂 tool schema、长期任务状态流和 Windows 全部 DAG 语义还未覆盖。

## 后续
P0 做客体实际可见可交互的 AIWS 主屏；完整 Windows 任务协议迁移；P1 构建 NixOS ISO/真实启动；受控 guest-only kernel 更新与隔离。小模型应独立评测、训练审计后再决定是否需要 LoRA，不得突破 host deny 策略。
