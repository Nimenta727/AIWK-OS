# 2026-11-21 · 工具审批机制底层（AI 启动程序 / 调用外部工具）

## 做了什么
- **`app.launch`（启动类写阶段）**：加入任务图的写工具集合（`aiws_toolplane.APP_LAUNCH_TOOLS` → `aiws_tasks.WRITE_TOOLS`），因此 Broker 自动要求持久化批准；创建任务、Broker、启动器三处都用 `aiws_apps.require_launchable` 校验（只能是登记的、命令固定的 gui 程序，且只有 `id` 一个参数）。
- **桌面启动器 `aiws_launcher.py`**：Agent 够不到显示，所以由工作台在用户会话里执行；它**不信任请求**，只读重新核对阶段“存在 / running / 已批准 / 参数恰为 {id} / 本次执行未用过”。Agent 的 `_run` 对 `app.launch` 走 `LauncherClient`；启动器不可用 → 阶段失败。工作台 `main()` 启动该服务；独立运行模式下由工作台自己在批准后启动。
- **声明式外部只读工具 `aiws_exttools.py`**：`ext.rg`、`ext.jq`、`ext.gitlog`、`ext.sqlite`；固定 argv、值在 `--` 之后、路径受限、环境清洗、超时/输出上限；sqlite 走 Python 只读连接 + 仅 SELECT 的授权器（不用会 `writefile()` 的命令行）。
- 工作台单元加 `BindPaths=-/tmp/.X11-unix`；`MODULES` 加两个新模块；文档 `docs/AIWS_TOOL_APPROVAL.md`。
- 本地模型 schema：`ext.*` 作为只读工具进入；**`app.launch` 没有放进模型可提议集合**（见下）。

## 验证
- Python 427 项通过（新增：`test_launch_approval`、`test_exttools`，以及 `test_apps` 的独立模式审批用例）。
- 端到端（真实 Agent + Broker + 启动器套接字 + 任务库，仅启动动作用替身）：未批准不能派发；批准后恰好启动一次；完成后不能重跑；启动器拒绝 pending/未批准/未运行/未知任务/参数不一致/重放/畸形请求；启动器缺失 → 阶段 failed。
- `rg`、`jq` 在本环境真实运行通过；sqlite 授权器拒绝 insert/delete/drop/pragma/attach/多语句/load_extension，数据库文件字节不变。

## 已知问题 / 未验证
- 真实客户机里：从 `PrivateTmp` 的 systemd 单元连接 X11（`BindPaths`）、真实启动 xfce4-terminal 等 **未验证**。
- 本地模型不能提议 `app.launch`：训练/留出数据没有样本，且 `test_model_dataset_v2` 要求每个可提议工具有样本。需要数据集 v3 + 重新评测。
- 启动器是同 UID 应用层防护，不是内核隔离。
- 用户在「工具」侧栏亲手点击仍是直接启动（不走任务图）。
- 没有注册任何写入类外部命令；框架留好了位置。

## 下一步
1. 在真实镜像里验证显示连接与启动（O6 检查清单）。
2. 数据集 v3：加入 `app.launch` 与 `ext.*` 样本，重新评测后再放开模型提议。
3. 评估 MCP 客户端接入：把外部 MCP 服务器的工具映射成声明式条目，沿用同一套分类与审批。
