# 2026-11-21 10:01 — Real UEFI A/B kernel boot fault-injection experiment

## 实施
新增 os/kernel/ci/uefi-ab-boot.sh：在一次性 CI 环境生成 GPT+FAT EFI 启动盘，以 OVMF 实际引导 systemd-boot。A 使用镜像的可信可启动内核+initrd，B 是保留相同内核但使用故意失败的 init 参数与 +2 引导计数，用于验证故障后重新启动并自动选择 A。真正加载 Live ISO 根文件系统，客户机没有主机共享、网络、设备直通。
原 aiws-os-image-boot.yml 新增 uefi-kernel-ab 作业，限带 [ab-boot] 的提交和显式 workflow_dispatch 执行，以免每次提交重复高成本 TCG 虚拟启动。只有串口发现 B 实际尝试、A 实际恢复以及 AIWS GUI 验收 PASS 才宣告通过。

## 限制/下一步
这属于带真实固件引导的失败回退实验，不能据此声称已具备多次真实内核升级和生产级防断电。必须观察 CI 实际运行结果；如果 EFI/QEMU 固件或系统服务失败要修复。后续对接客户机安装磁盘中的 boot manager、用户授权及 root broker，并补成功 B 升级与健康确认测试。
