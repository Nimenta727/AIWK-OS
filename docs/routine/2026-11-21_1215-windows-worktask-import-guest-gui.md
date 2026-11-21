# 2026-11-21 12:15 — AIWS Shell Windows 历史工作流导入与真实图形点击验收

## 修改
- `GuestTaskStudio.tsx` 的 DAG 页面增加单个 Windows WorkTask JSON 的客户机文件选择入口，只提交到同一虚拟机 127.0.0.1 API；额外加 12 KB 客户端预检和最终 16 KB JSON 请求限额。
- 导入后自动打开同一 Agent SQLite 中的任务详情，展示原始 Windows Agent 名称/状态、源 SHA256、不可执行 UNMAPPED 明示，并隐藏执行/审批按钮（原阶段从未绑定 Linux Tool）。
- `aiws_gui_smoke.py` 在真实 QEMU 客户机创建完全合成的 Windows WorkTask fixture，通过 ChromeDriver `input[type=file]` 模拟浏览器的真实文件选择，要求导入后两个阶段均 UNMAPPED、无任何执行按钮，增加独立串口验收证据。
- 不要求模型在线、不调用云端、不允许旧 Windows 指令隐式执行，也不访问虚拟机宿主文件。
- 修改：`desktop/AIWorkstation.Frontend/src/os/GuestTaskStudio.tsx`、`os/debian/config/includes.chroot/usr/local/lib/aiws/aiws_gui_smoke.py`、本 routine 与索引。

## 验证与限制
- 这轮必须等真实 npm TypeScript 构建、Linux ISO、QEMU Chromium GUI 测试才可声明通过。新 UI 依靠浏览器 file picker；用户必须在虚拟机内部拥有导出的 WorkTask JSON。
- 仍未实现旧 Windows Agent/ClaudeCode/Codex 执行适配；原任务作为历史证据导入后不可执行是有意安全约束。
- 仅导入 32 阶段、最大 12 KB 的小型历史任务。大型迁移文件需要独立批处理和审查。
- Windows 历史数据与本地模型训练数据严格分开：未经授权不能拿旧 prompts/结果作模型微调。

## 下一步
1. 用 CI 结果修复 ChromeDriver 选择文件的真实问题；留存 GUI 与 agent 重启 receipt。
2. 建立后续**人工审阅后**映射 Windows 阶段到客体工具的受控工作流与可撤销迁移记录。
3. 追踪 2B 离线模型真实 CPU 推理/QEMU 模型包构建，增加正式测试集。
