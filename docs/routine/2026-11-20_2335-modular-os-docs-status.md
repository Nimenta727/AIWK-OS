# 2026-11-20 23:35 — Record OS framework selection and module split

## 中文
变更：更新仓库 README、docs 首页、routine 索引和新增 docs/AIWS_MODULAR_OS.md。明确 NixOS 声明式 OS 与 Debian Live 首轮启动实验并行、共享 React 前端与 Python Agent 运行时，后续可接 mkosi / Fedora bootc。
涉及文件：README.md, docs/README.md, docs/routine/README.md, docs/AIWS_MODULAR_OS.md，以及本次 routine。
验证：此前 Native Windows Desktop EXE 编译/测试成功，NixOS 配方已在 AIWS OS image/boot workflow 通过解析与求值；Debian 真实 ISO 构建正在执行，尚无开机通过证据。
已知限制：Linux 的完整 Windows 任务编排、自主 LLM Agent、特权 Broker、可复现镜像与隔离验收均尚未完成。
下一步：获取 Debian ISO/QEMU 结果并修复失败；固化 Nix/npm lockfile；统一任务模型与 GUI 验收。

## English
Document distro-neutral OS boundaries, researched NixOS/mkosi/bootc/Yocto/Buildroot tradeoffs, live build/boot evidence gates and the ongoing limits of the guest controller.
