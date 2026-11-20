# 2026-11-20 17:30 — 计划中心 V1.7.1 正式 Windows CI 打包核验

## 改动与版本确认
- 对应代码版本为 `45cf7097e2aeb8888b66bf64f80bcb0175ed7c97`，涵盖计划中心及 Windows EXE `1.7.1` 版本元数据修正。
- Native Windows Desktop EXE：Actions [44708896256](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708896256)，成功。包含前端 TypeScript/React、WPF/.NET、核心烟雾测试、自包含 EXE 与 ui-dist 打包。
- Python & Windows checks：Actions [44708896217](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44708896217)，成功。
- 从成功 CI 运行下载原生二进制并验证 ZIP 内包含 WindowsAIWorkstation.exe、ui-dist/index.html、Plan Studio 对应 JS 文本。
- 运行包 SHA256：`a9d290d765b89df4461900f3dbb54e780737627f9c8fd98028ea57e84879606f`。
- 本次只更新验收文档与本 routine 记录；不变更已验收的运行时代码。

## 涉及文件
- `docs/PLAN_STUDIO_V171.md`
- `docs/routine/2026-11-20_1730-plan-studio-final-windows-release.md`

## 尚未验收的部分
- 用户 Hyper-V 虚拟机内的可视化交互、3 秒文件监测与终端同时运行、权限问题、数据持续更新；CI 成功不是图形交互实测。
- CLI 内部未保存到 Markdown 的计划不可直接观察；不虚构实时模型状态。

## 下一步规划
1. 在 Hyper-V VM 进行真实多份计划书、频繁修改、大文件和多任务工作流的手工交互验收。
2. 建立可选的用户批准的计划粘贴导入和本地持久化（保护隐私、拒绝无意持久化模型敏感输出）。
3. 发展带稳定节点 ID 的计划语义格式与版本比较，在模型输出有官方事件支持时再接入真正的流式计划更新。
4. 维持 V1.8 权限 Broker 和系统安全审查独立路线，不因计划中心完成而降低安全门槛。
