# 双盘与权限分离（系统文件形式）

## 做了什么
- **系统盘**：仍是只读的 Live 镜像（squashfs）。因为 live-boot 在上面叠了一层可写的内存层，改过的文件原本不会被发现，所以镜像构建的最后一步生成清单 `system.sha256.json`，每次开机由 `aiws-verify-system.service` 比对，结果写入 `/run/aiws/system-verify.json`，工作台会显示“系统文件被改动”。只报告，不修复、不删除。
- **工作盘**：第二块虚拟盘，卷标 `AIWS-WORK`，btrfs，挂载在 `/srv/aiws-work`，选项 `noexec,nodev,nosuid,noatime,compress=zstd`（放在上面的东西不能被执行）。AI 的工作文件在子卷 `work`，只读快照在 `.snapshots`，保留最近 20 个；回滚会先把当前状态存成快照，所以回滚本身也能撤销。由 `aiws-work-disk.service` 开机时设置。
- **格式化的保险**：只有“恰好一块、整盘、未挂载、无分区表、无文件系统签名、无卷标、≥1 GiB、非可移动、非只读”的盘才会被格式化，并且格式化前再用 `blkid` 复核一次；有任何签名/不同卷标/多块空盘一律拒绝。
- **用户**：`sysusers.d` 创建登录名为 `aiws-agent`、`aiws-broker` 的无登录账户和组 `aiws-work`；工作树的 ACL 只给登录用户和 `aiws-agent`。
- **宿主启动**：`os/host/run-qemu-offline.sh` 新增可选环境变量 `AIWS_WORK_DISK=/绝对路径/work.qcow2`（先用 `qemu-img create -f qcow2 work.qcow2 40G` 创建）。

## 没做 / 没验证（如实）
- **Agent 与 Broker 仍作为登录用户的 systemd 用户服务运行**，还没有迁到 `aiws-agent`/`aiws-broker` 账户：它们的套接字路径、状态目录、与工作台的通信都要跟着改，必须在能启动的镜像里逐项试，这里不盲改。所以“三用户分离”目前只完成了账户和文件权限这一层，进程层还没有。
- 没有在真实镜像里验证：服务的启动顺序、live-config 与 ACL 的先后（单元里写了 `After=live-config.service`）、`btrfs-progs` 是否已在包列表（已加入）、`noexec` 对工作区里的构建/测试命令的影响（需要执行的构建应在带 exec 的位置进行，这是已知取舍）。
- 清单只覆盖镜像自带文件；`/usr/local/bin`、`/etc/systemd/system` 只校验“已列出的文件有没有被改/删”，不报“多出来的文件”（开发者会往里装东西）。
- 没有 dm-verity 级别的启动前校验（那需要自定义内核/initramfs）。

## 用法
`sudo python3 /usr/local/lib/aiws/aiws_workdisk.py snapshot 重构前` · `... list` · `... rollback 20261122T060000Z`
