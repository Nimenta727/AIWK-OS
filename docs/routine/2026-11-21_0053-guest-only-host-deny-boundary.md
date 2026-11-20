# 2026-11-21 00:53 — Host-deny, guest-only Agent runtime boundary

## Scope / 政策
按照用户最新要求，**无论 AIWS 内核或 Agent 能力扩展到什么程度，用户宿主系统始终不在任何可调用权限范围内**。客户机可以使用自己的工作区、内核源码和服务；所有 host 文件、host 内核、宿主 Hypervisor 控制、文件夹共享、guest agent、设备直通、主机凭据和 host shell 操作均不向 Agent 提供。

## 具体修改
- 新增 os/runtime/aiws_guest_boundary.py：普通用户 + 镜像标记 + 真实 VM 检测联合开机前检查。拒绝典型宿主/共享目录位置、9p/virtiofs/vboxsf/CIFS/NFS 等共享文件系统，拒绝受控 workspace 中的任意嵌套挂载点。
- 将守卫接入 os/runtime/aiws_toolplane.py 的工作区解析和文件路径解析、os/runtime/aiws_workbench.py 客户机服务 main()，降低在裸机错误启动 Agent、跨越 guest 工作区访问外部挂载的风险。
- Debian 13 Live adapter 的运行时打包包含 guest_boundary，镜像写入 /etc/aiws/guest-managed；NixOS 模块声明相同标记。
- 新增 os/verify/test_guest_boundary.py：无标记/错误标记/VM 检测失败/root 进程、外部共享/嵌套挂载拒绝、发行版配置与离线 launcher 检查。
- 影响文件：os/runtime/aiws_guest_boundary.py, os/runtime/aiws_toolplane.py, os/runtime/aiws_workbench.py, os/debian/build.sh, os/debian/config/includes.chroot/etc/aiws/guest-managed, os/platforms/nixos/aiws.nix, os/verify/test_guest_boundary.py, 本 routine。

## 验证与限制
测试新增但需由本次 CI 实际执行；此前镜像 Kernel/LightDM/XFCE/HTTP/MCP 的直接内核启动 smoke 在 workflow run 44762589191 通过。
这只是 **defense-in-depth**：VM 检测和 guest marker 无法抵御故意以 guest root 伪造环境；当 hypervisor 错配或有漏洞时，无法绝对保证 host 安全。有效的 host 隔离必须依靠受限制的 VM 管理程序、无宿主目录映射与直通、禁止 hypervisor control socket/agent channel、宿主更新与外部审计。此提交不向 AI 提供宿主权限，也不提供无审查的 live kernel 修改。

## 下一步
- AI 自动管理 guest workspace 的安全文件浏览、搜索与快照；共享 UI 取消传统文件管理器为主入口。
- 可选小模型仅在客户机本地调用与加载；不得触发宿主网络、GPU 直通或主机设备命令。
- kernel 源码变更先进入隔离构建、检查、版本化镜像和回滚流程，绝不修改 host kernel。
- real boot/GUI 和独立安全验收。
