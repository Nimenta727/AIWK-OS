# M1 Installer & Recovery / 安装与恢复

**当前仅提供只读预检，不提供可执行安装器。** 这是有意的安全门槛：分区、格式化、写入 EFI 和回滚如果没有完整端到端验证，不能对用户磁盘执行。

```bash
python3 os/installer/aiws_install_preflight.py --json
python3 os/installer/aiws_install_preflight.py --install  # 必然拒绝，退出码 3
```

预检只读取虚拟化状态、UEFI 目录和 lsblk JSON；只列出未挂载、无子分区、非可移除、至少 32 GiB 的候选磁盘。它**不**将候选盘视为已经授权安装，也不保证设备空白或无重要数据。物理机安装明确禁止。

## M1 完成前的强制验收

1. 在隔离 QEMU/OVMF、一次性 qcow2 虚拟磁盘中完成交互式确认，绝不使用宿主磁盘。
2. GPT/EFI 与根文件系统可重复构建；安装后移除 ISO 仍能独立启动。
3. 用户数据独立持久化；多次重启后的哈希、权限和所有者一致。
4. 更新 A/B 切换、故障注入、回滚后数据完整性与日志可审计。
5. 不存在隐式磁盘擦除、自动选盘或宿主共享；测试明确验证拒绝路径。

**English:** This is a non-destructive installer preflight, not a disk installer or a rollback system. The write path remains disabled until real disposable-VM acceptance and recovery evidence exist.
