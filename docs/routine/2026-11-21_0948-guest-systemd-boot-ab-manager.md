# 2026-11-21 09:48 — Guest systemd-boot A/B staged kernel trial and recovery manager

## 本次实现
- 新增 os/runtime/aiws_boot_slots.py：只在客户机 root + 标记 + VM 检查后、并且已挂载独立 vfat EFI System Partition 的情况下操作。A 为已有 known-good systemd-boot 入口，不可删除；B 从客户机本地信任 SHA-256 的内核和 initrd 文件写入另一槽，生成带 +3 boot counting 的 BLS 启动项。
- --try-b 经用户显式 --confirm-guest-root 后保留 A 为默认并设置 B 的一次性引导；若 B 无法启动并发生再次启动，systemd-boot 可回退 A。--rollback-a 恢复默认 A，--commit-b 只在已从 B 引导且版本一致、工作台与独立 Agent 健康且 boot entry 获 systemd-bless-boot good 后将 B 设为默认。
- 不暴露 Agent 或 HTTP 的任意 root/bootctl API，工作台的 kernel.stage 仍仅限候选配置；root CLI 属于独立客户机安装/恢复实验。没有调用宿主 VM 或改变宿主内核。
- 新增 os/verify/test_boot_slots.py，验证 A 保留、B 哈希完整性、一次性 boot 命令参数、明确 A 回退、路径/哈希拒绝。

## 验证限制
静态单元测试不等于真实 OVMF/UEFI 启动，后续必须在持久化虚拟硬盘中通过成功和失败两种故障注入，否则不能声称已验证自动回滚。遇到内核死机不重启时，boot counting 无法单独保证恢复，需要 guest/watchdog 机制。系统目前仍是 Live ISO，默认没有 ESP 版本槽；真实 A/B 机制只适用于经过专门安装的 guest systemd-boot 镜像。

## 下一步
构建专门 QEMU OVMF + FAT ESP 双启动项镜像，测试 B 故障自动重启后的 A 恢复、B 成功健康标记与默认切换；之后再考虑创建单独特权 broker 的严格权限许可机制。另需真 Qwen GGUF 客体运行和评测。
