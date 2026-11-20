# 2026-11-21 03:28 — Real QEMU guest GUI acceptance covers approved kernel candidate staging

## 本次改动
- 扩充 os/debian/config/includes.chroot/usr/local/lib/aiws/aiws_gui_smoke.py：在专用一次性 Debian 虚拟机中生成安全的 CONFIG_VIRTIO/SECCOMP .fragment 测试文件。
- 经真实 Selenium/Chromedriver 点击 AIWS 系统与安全页面，创建 kernel.stage 候选任务、读取 SQLite 持久 DAG，显式点击“批准客体写操作”再点击执行，验证 candidate-only 结果及 deployed:false。
- 原有 AI 文件管理、DAG 任务、默认离线模型禁用验收仍保留；任何一环异常会拒绝串口 AIWS_BOOT_SMOKE_PASS。不会更改运行中的内核、宿主机、bootloader 或 Hypervisor。

## 验证/下一步
此时是增强验收测试代码的提交，必须等待新 Github Actions 实际 ISO 构建、QEMU 启动与用户界面点击结果，才能称通过；目前不存在真实 A/B boot recovery 验收。下一步解析 CI 日志，修复任何失败；引入独立可重启 kernel build VM、合法/可验证 initrd 与 boot-slot preflight、可还原快照，不提供无审核 root 控制通道。
