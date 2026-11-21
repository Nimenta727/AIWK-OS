# 2026-11-21 10:31 — Package interactive guest EFI kernel A/B manager in Debian ISO

## 实施
- Debian ISO 打包脚本新增 aiws_boot_slots.py 供安装在拥有持久 EFI System Partition 的客户机使用；新增 `/usr/local/sbin/aiws-kernel-slots` 守卫启动入口，要求用户已进入客体管理员会话，运行脚本本身再次核验客体虚拟机标记和 root、实际 ESP、SHA256 可信内核及 initrd、明确 `--confirm-guest-root`。工作台和 AI 模型均没有调用 root bootloader 的 HTTP/Agent 权限。
- 只允许在已经安装好 A 可引导项的客户机进入 B 暂存和一次性启动流程。当前默认 Live ISO 没有持久 ESP，因此调用时应拒绝，并非自动执行真实内核替换。
- 这项修改不会删除主机或已有客户机分区，不会触碰宿主磁盘或设备直通。
## 修改文件
os/debian/build.sh；os/debian/config/includes.chroot/usr/local/sbin/aiws-kernel-slots；本 routine。
## 下一步
检查实际 OVMF B→A 回退 CI、独立 VM EFI 安装镜像与用户授权 bootctl 集成；补全故障重启、定时健康确认。仅单元测试通过不能标记可靠 A/B 完成。
