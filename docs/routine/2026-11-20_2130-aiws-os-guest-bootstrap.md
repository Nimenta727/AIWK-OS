# 2026-11-20 21:30 · AIWS OS P0 independent guest bootstrap

## 中文
**变更：** 确认用户要求的是独立运行的虚拟机操作系统，不是 Windows AIWS 外挂功能。新增 Debian 13 live-build ISO 工程、XFCE + Firefox ESR + Geany、多语言开发包、内核配置设计片段、客户机 sysctl、安全诊断和交互式客户机 root shell。新增 KVM 宿主离线启动脚本（拒绝宿主 root、不加网络/共享文件夹）、静态安全回归测试与中英双语架构文档；主 README 和文档索引添加入口。

**影响文件：** `os/**`、`docs/AIWS_OS_BLUEPRINT.md`、`docs/README.md`、`README.md`、`.github/workflows/aiws-os-static.yml`、本记录。

**验证：** 静态 unittest 与 bash -n 由新 workflow 运行，提交时没有声称执行镜像构建、KVM/Hyper-V 启动、内核编译或逃逸安全验证。CI 结果必须在 Actions 上独立核查。

**已知问题：** 原 WPF/WebView2 AIWS Core 尚未移植到 Linux；当前阶段客户机已有系统/开发工具但没有完整 AIWS Linux GUI/Agent broker。root 能更改 guest 策略，因此 guest 内 sysctl 不能保护宿主；镜像包许可证仍需审查；默认离线模式无法调用云端 Agent。

**下一步：** (1) 运行静态 CI 并修复问题；(2) 在 Debian 13 builder 真正生成 ISO、校验校验和并启动 KVM/Hyper-V；(3) 设计可离线/在线切换的宿主强制网络策略；(4) Linux 版 AIWS Core 服务、React 桌面桥接和权限 Broker；(5) 受测的自定义内核与 license/SBOM/升级回滚。

## English
Change: add an independent Debian 13 AIWS guest OS image recipe, XFCE/browser/editor/languages, guest kernel policy and a **design-only** custom kernel fragment, interactive guest root, an offline/no-sharing unprivileged KVM launcher, and regression contracts. Update navigation/documentation. Validation: static tests scheduled in CI; no boot, kernel build or VM escape validation has been performed. Limitations: existing Windows agent host is not yet ported, and customer/guest root is not an external isolation boundary. Next: confirm CI, build/boot actual ISO, design host-enforced network, port agent host, implement broker, verify licensing.
