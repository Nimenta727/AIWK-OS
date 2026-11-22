# 2026-11-22 09:00 — S4/S5：本地模型常驻、宿主推理服务与基准、双盘系统文件

## 改动
- **模型常驻**：模型网关新增常驻模式（`--idle-seconds 0` / `--resident`）：启动即加载，不因空闲卸载，进程死了自动拉起；崩溃冷却照旧，坏模型不会空转。两个客体启动脚本默认常驻，`AIWS_MODEL_RESIDENT=0` 可退回按需加载（内存紧张的机器用）。
- **宿主推理**：`os/host/aiws_host_model.py`（宿主上守护 llama-server：只绑 127.0.0.1、指数退避重启、`--check` 对照你的 llama-server 帮助输出验证每个参数仍存在）；`os/model/bench/host_bench.py`（冷/热/前缀复用三种延迟与 tokens/s，数字取自服务器 usage，缺失记 null，只接受回环地址）。默认参数面向 12 GB 显存：全部层上 GPU、flash-attn、KV 缓存 q8_0、单槽、`--cache-reuse`、16k 上下文——**这些是起点，必须用基准实测后再调**。
- **双盘与校验**（`docs/AIWS_DUAL_DISK.md`）：`aiws_workdisk.py`（工作盘 AIWS-WORK，btrfs，`noexec,nodev,nosuid`，子卷 + 只读快照 + 回滚前自动留档；只格式化“恰好一块的空白整盘”，格式化前再复核）、`aiws_sysverify.py`（镜像构建末尾生成 sha256 清单，开机比对，结果写 `/run/aiws/system-verify.json`，工作台出横幅）、两个 systemd 单元、sysusers（`aiws-agent`/`aiws-broker`/组 `aiws-work`）、tmpfiles ACL、宿主脚本可选第二块盘 `AIWS_WORK_DISK`、状态栏“工作盘”。
- **顺带发现并修复的真实缺陷**：Python 的 `$` 会匹配结尾换行，导致 `^...$` 校验的 id 可以带尾部换行；已在宿主脚本及运行时 8 处校验器改用 `\Z`，并加回归测试。

## 验证
- Python 全量 549 项通过（2 项跳过为既有）；前端 `tsc`/`npm test` 40 项/`vite build` 通过。
- `systemd-analyze verify` 对两个新单元无告警；`systemd-sysusers --dry-run` 能解析并创建三个账户/组；`systemd-tmpfiles` 能解析（ACL 行在无这些账户的临时根里无法应用，属预期）。
- 常驻模式用合成的假 llama-server 测过：启动即加载、不卸载、首个请求不付冷启动、被 SIGKILL 后自动恢复、起不来的模型受崩溃冷却限制；连跑 3 次稳定。
- **未验证**：真实 GPU 上的任何数字（显存、tokens/s、前缀缓存收益）；这些参数名是否与你的 llama.cpp 版本一致（用 `--check`）；真实镜像里的开机顺序、live-config 与 ACL 的先后、`noexec` 对工作区构建的影响；btrfs 格式化与快照/回滚（只测了决策与命令序列，没碰真实磁盘）。

## 已知问题 / 未做
- **Agent 与 Broker 还没迁到 `aiws-agent`/`aiws-broker` 账户**（仍是登录用户的用户服务）；账户和文件权限已备好，进程迁移要在可启动的镜像里逐项试。所以“三用户分离”只完成了一半。
- 工作盘 `noexec` 意味着需要执行脚本/二进制的构建要放在有执行权限的位置，这是有意的取舍。
- 4 个旧页面仍未按新规范重写；云端 CLI 字段需要真机录制校对（O6）。

## 下一步
1. 在真实镜像里启动，核对外壳、输入法、工作盘、系统校验横幅；2. 宿主上跑 `aiws_host_model.py --check` 与 `host_bench.py`，据数字调参数；3. Agent/Broker 迁到专用账户；4. 重写 4 个旧页面；5. 用真实 Claude Code 输出校对子智能体树字段。
