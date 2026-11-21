# 2026-11-21 11:14 — Fix OVMF/systemd-boot preflight on Ubuntu 26.10 runner

## 根因
真实 GitHub OVMF A/B 工作流 44850151109 通过 Debian ISO build 与直接 kernel GUI boot，但 `uefi-kernel-ab` 一启动就 exit 1，boot-serial/log 文件都不存在。检查发现 `set -Eeuo pipefail` 下使用 `find <不存在的候选目录> | head -n1` 检测 EFI 文件，在部分 Ubuntu 发行版查找目录不存在时整条赋值命令直接失败；固件根本没有加载。
## 修复
- 替换为显式候选文件路径循环，支持 unsigned 和 signed systemd-boot EFI；OVMF code/vars 必须来自同一目录且尺寸版本匹配，兼容 4M/常规 VFAT 固件布局。
- 缺失时打印 AIWS_AB_PRECHECK_FAIL 和可用文件目录证据，不再沉默退出。
- 修改 os/kernel/ci/uefi-ab-boot.sh、本 routine；提交包含 [ab-boot] 再次触发真实固件验收。
## 下一步
观察 QEMU 真正读取 GPT/ESP→B 故障→A 回退及 AIWS_GUI_BROWSER_PASS；若后续仍失败根据串口和镜像内容继续修复。直到 `AIWS_AB_FIRMWARE_FALLBACK_PASS` 才可说 UEFI 回退验收通过。
