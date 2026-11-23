# 2026-11-23 12:54 — ISO 构建/发布不稳定的审计与修复

## 背景
用户："帮我查一下这个怎么一直不稳定，特别是构建 iso 时，你帮我审计一下"。
我逐条读了两条工作流的失败日志：`release-preview.yml` 共 14 次运行（1 次成功是第 8 次，现在第 14 次也成功了），以及 main 上的 `aiws-os-image-boot.yml` 最近 10 次（没有一次成功）。

## 每次失败的直接原因

### 发布流程 release-preview.yml
| # | 结果 | 直接原因（日志原文） | 类别 | 现状 |
|---|---|---|---|---|
| 1 | 失败 | `PREVIEW.env: line 7: syntax error near unexpected token '('`（值没加引号） | 自己引入 | 已修（有测试） |
| 2 | 失败 | Code-OSS gulp：`Cannot read .../github-authentication/tsconfig.json`（删扩展删早了） | 上游构建图假设 | 已修 |
| 3 | 失败 | gulp `-ci` 任务只打包：`ENOENT .../out-vscode-reh-web-min/nls.keys.json` | 上游构建图假设 | 已修 |
| 4、5 | 取消 | 连续推送，前一个被手动取消 | 流程 | — |
| 6、7 | 失败 | QEMU：`Could not open .../out/boot-serial.log: Permission denied`（容器以 root 建出 `out/`） | 工作流设计 | 第 8 次修好 |
| 8 | **成功** | 发布 v0.2.0-preview.1 | | |
| 9 | 失败 | 合并到 main 时 PREVIEW.env 又触发一次：`a release with the same tag name already exists`（白跑 34 分钟） | 工作流设计 | **本次修** |
| 10 | 失败 | 构建容器里没有 `python3`（build.sh 新加了 python3 调用） | 自己引入 | 已修（有测试） |
| 11 | 失败 | 下载权重：`curl: (22) ... error: 502`（HuggingFace 暂时故障） | 外部依赖 | 权重已移出发布 |
| 12 | 取消 | 我推送时带着失败的测试，自己取消 | 自己引入 | 已改为推送前跑全量 |
| 13 | 失败 | 镜像内 GUI 冒烟脚本还用旧界面的选择器 | 自己引入 | 已修 |
| 14 | **成功** | v0.3.0-preview.1 | | |

### main 上的镜像启动验收 aiws-os-image-boot.yml（一直红）
- `firmware-iso-boot (bios)` 和 `(uefi)`：每次都在等满约 22 分钟后失败，串口上**连内核的一行输出都没有**。
  - **根因（本次查实）**：live-build（trixie 20250505）的启动菜单默认**永远等待**：`isolinux.cfg` 里是 `timeout 0`（syslinux 的 0 表示不超时），GRUB 的 `config.cfg` 里**根本没有** `set timeout`（GRUB 不设就一直等）。我下载了 Debian 的 live-build 包核对过模板原文。
  - 分支上已有的钩子 `9010-aiws-boot-menu.hook.binary` 修好了 BIOS（把 `timeout 0` 改成 3 秒），但对 GRUB 只会"改写已有的 `set timeout=`"，而模板里没有这一行，所以 **UEFI 菜单仍然永远等待**。这个钩子还没合到 main，所以 main 上 BIOS 也是红的。
  - 次因：这个测试硬编码 `accel=tcg`（纯软件模拟），即使机器有 KVM 也不用，启动慢好几倍。
- `debian-boot`（第 69 次）：GUI 冒烟脚本找不到旧界面按钮，属于上表第 13 次的同一问题，分支上已修。

## 结构性原因（为什么"一直"不稳）
1. **真正的镜像只在发布那一刻第一次被构建和启动。** 镜像启动验收只在 main 上跑，分支上的改动（新 python3 调用、界面重做）要到发布才暴露；每暴露一个问题就是一次约 30 分钟的往返。14 次里有 5 次是这种"自己改了 A，没想到镜像里的 B 依赖它"。
2. **镜像里的脚本没有仓库级测试。** 启动菜单钩子、GUI 冒烟脚本、build.sh 对容器工具的依赖，以前都不在 `os/verify` 里；现在后两者有了，本次补上第一个。
3. **外部下载没有重试/没有缓存**：HuggingFace（已移除）、GitHub 上的 llama.cpp、Code-OSS 上游。
4. **发布标签只能用一次，但工作流开头不检查**，等到最后一步才发现。
5. **直接用 `full` 阶段试错**，`iso-dry` 阶段很少用。

## 本次改动
- `os/debian/config/hooks/normal/9010-aiws-boot-menu.hook.binary`：GRUB 没有超时设置时**追加** `set timeout=3`（`config.cfg` 在菜单项之前被 `grub.cfg` source）；已有的照旧改写；可重复执行。
- `os/verify/test_boot_menu_hook.py`（新）：用 live-build 模板原文做夹具运行钩子，验证 BIOS 和 UEFI 都会超时、重复运行无变化、缺文件不失败。**变异检验**：换回旧钩子，UEFI 那条测试失败。
- `os/kernel/ci/firmware-iso-boot.sh`：有可写的 `/dev/kvm` 就用 KVM，否则 TCG（打印所用的加速方式）。
- `.github/workflows/aiws-os-image-boot.yml`、`release-preview.yml`：启动前加一步让 runner 用户能打开 `/dev/kvm`（GitHub 文档给的 udev 规则；没有 KVM 时退回软件模拟，不会失败）。
- `release-preview.yml`：
  - 第一个作业就检查标签：`full` 阶段且该标签已有发布 → 若是推到默认分支（合并）就**跳过**并留通知，否则**10 秒内失败**并说明要换标签。
  - 新增 `skip` 阶段，三个构建作业都据此跳过；ISO 作业只在 `iso-dry`/`full` 时运行。
  - llama.cpp 的 clone/fetch 加 4 次重试（间隔递增）。

## 验证
- Python 全量：**918 通过，2 跳过**（含新增 5 项）。
- 两个工作流 YAML 能解析；`firmware-iso-boot.sh` 通过 `bash -n`。
- **没有在 CI 上验证**：启动菜单超时要等下一次镜像构建才能真正证明 UEFI 能进到内核；KVM 步骤在 GitHub 托管 runner 上是否生效要看日志里的 `QEMU acceleration`/`AIWS_FIRMWARE_ISO_ACCEL`。这次推送**不会**触发发布（没改 PREVIEW.env），镜像验收只在 main 上跑。

## 已知问题
- 分支上没有自动的镜像构建/启动测试；合并前仍然要靠发布流程或手动触发。
- Code-OSS 上游构建（约 1 小时）没有缓存。
- `aiws-real-model.yml`、`uefi-ab-boot.sh`、`aiws-os-image-boot.yml` 的 `debian-boot` 作业仍硬编码 `accel=tcg`（它们用 `-kernel` 直启，不受菜单问题影响，只是慢）。

## 下一步
1. 用 `workflow_dispatch` 手动跑一次 `aiws-os-image-boot.yml`（指向本分支）验证 UEFI/BIOS 菜单修复和 KVM——需要你同意再触发。
2. 让镜像启动验收在 PR 上也运行（至少改动 `os/debian/**`、`os/runtime/**`、`workbench/src/**` 时），这样问题在合并前暴露，而不是在发布时。
3. 发布前约定先用 `iso-dry`，绿了再改成 `full`。
4. 缓存 AIWS Code 构建产物（按上游标签 + 构建脚本哈希做键）。
5. 其余 `accel=tcg` 的地方同样改成自动选择。
