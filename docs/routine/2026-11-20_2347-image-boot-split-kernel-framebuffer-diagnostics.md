# 2026-11-20 23:47 — Split ISO build from QEMU boot and add direct kernel diagnostics

## 中文
**实测故障：** run 44758470948 成功构建并上传 Debian Live smoke ISO（约 945 MB），NixOS eval 成功；QEMU 能启动进程但 12 分钟未收到任何 ttyS0 日志，客体开机未通过。单靠空串口不能判定是引导菜单、内核还是图形服务失败。
**改动：** 将 GitHub Actions 镜像构建与虚拟机测试拆成 debian-image 和 debian-boot 独立作业，前者上传 ISO+SHA、后者下载当前工作流生成的同一镜像（失败时可针对 boot job 单独重跑）。加入 xorriso 引导目录/El Torito 探查、从 ISO 提取 Linux kernel/initrd 后以 QEMU -kernel/-initrd 明确串口参数启动，并通过宿主 HMP 监视器定期导出虚拟屏幕 PPM 帧；无 VM NIC、无宿主共享目录或 guest agent 通道。
**影响文件：** .github/workflows/aiws-os-image-boot.yml、本 routine。
**验证：** 此提交须运行新的 CI；不预先称内核已启动。直接载入 kernel 绕过 ISO BIOS/GRUB 菜单，只能作为客体 kernel+service 诊断，**不等于完整 ISO 固件启动验收**。
**限制：** hosted runner 依旧没有 KVM，QEMU TCG 性能与真实 VM 有差异；GUI 进程级验收与实际人机点击仍不同；NixOS 尚未真实构建镜像。
**下一步：** 收集 ttyS0/虚拟显示证据并定位故障，针对 boot 单独重跑；补充正常 El Torito/UEFI 引导验收；验证 GUI 工作台点击、统一任务模型、权限 broker 和宿主侧隔离。
## English
After a real 945 MB ISO build, an empty serial trace blocked guest boot acceptance. Split build and boot CI to reuse the same artifact, inspect El Torito/live files, boot the guest kernel with explicit serial args and collect host-only QEMU framebuffer evidence. Direct-kernel diagnostics do not prove native firmware ISO boot.
