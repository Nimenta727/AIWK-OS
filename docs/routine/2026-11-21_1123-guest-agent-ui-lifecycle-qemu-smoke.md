# 2026-11-21 11:23 — In-VM systemd workbench/Agent restart recovery acceptance

## 功能
- 新增 os/verify/aiws_guest_lifecycle_smoke.py（随 Debian ISO 安装）：在独立客户机中确认系统健康与至少两个真实 GUI 创建 DAG 后，先重启 aiws-workbench.service，验证独立的 aiws-agent.service PID 没变、UI PID 已更新、任务 ID 没丢；然后重启 aiws-agent.service，确认新 Agent 健康、原有任务和审计哈希链仍完整。
- Debian aiws-boot-smoke 加入独立 systemd user service 生命周期强制校验，未输出 AIWS_GUEST_LIFECYCLE_PASS 不能输出最终 AIWS_BOOT_SMOKE_PASS。使用 guest 当前用户固定服务和只读 localhost 接口，不触碰主机、root、kernel bootloader 或共享目录。
- Debian build.sh 打包 lifecycle smoke Python 脚本，不依赖外部网络。
## 文件
os/verify/aiws_guest_lifecycle_smoke.py、os/debian/build.sh、os/debian/config/includes.chroot/usr/local/bin/aiws-boot-smoke、本 routine。
## 下一步
必须看到真实 QEMU ISO 启动与 Selenium 点击的 CI 通过；系统服务 PID 变化和审计恢复是新增的验收门槛。随后做故障注入断电重启（持久盘）、A/B 固件真实回退和模型离线大样本 eval。
