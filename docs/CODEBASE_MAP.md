# 代码结构与模块职责 / Codebase map

**适用范围：** 当前工作树。描述实际源码归属，不把设计目标当成已实现功能。旧代码（Windows 工作台、旧 Python 控制平面、NixOS 配方）已移入 Git 历史，见 [history/README.md](history/README.md)。

```text
AIWK-OS/
├── README.md  CHANGELOG.md  NOTICE  LICENSE  AGENTS.md
├── workbench/            # React 工作台前端（VS Code 风格外壳 + 观察台）
├── os/
│   ├── runtime/          # 客户机 Python 服务（MODULES = 装入镜像的模块清单）
│   ├── debian/           # live-build 配方、软件包清单、systemd 单元、桌面 Shell
│   ├── ide/              # AIWS Code：Code - OSS 重新品牌化的构建配方、补丁、品牌
│   ├── builder/          # 官方 CLI 构建通道的隔离配置与自检
│   ├── model/            # 本地模型运行器、数据集生成、评测（CI）
│   ├── kernel/ installer/ host/   # 内核选项与固件启动诊断 · 只读安装预检 · 无宿主共享的 QEMU 脚本
│   └── verify/           # 静态契约与行为测试（Python unittest）
├── .github/workflows/    # CI 与发行构建
└── docs/                 # 当前文档；history/ 旧资料；routine/ 每次修改的记录
```

## 运行时（`os/runtime`）

| 模块 | 职责 | 约束 |
| --- | --- | --- |
| `aiws_workbench.py` | 仅 127.0.0.1 的 HTTP 服务：UI 静态资源、观察台/任务/模型/构建/工具 API、文件原始预览 | 不直接拥有执行权；写类操作走审批 DAG |
| `aiws_agent_service.py` / `aiws_agent_client.py` | 沙箱化 systemd 用户 Agent：持久 DAG 调度、工具执行 | 经 Broker；不能以 UI 布尔值替代审批 |
| `aiws_permission_broker.py` | 独立同 UID UNIX Socket 策略决策、阶段校验、一次性回执 | **不是**内核强制隔离 |
| `aiws_tasks.py` | SQLite DAG、状态转换、审批、哈希链审计 | |
| `aiws_toolplane.py` | 工具目录与低层工具实现 | 路径受限，不跟随符号链接 |
| `aiws_exttools.py` | 声明式外部只读命令（rg / jq / git log / sqlite SELECT） | 固定 argv、`--` 之后传值、输出有界 |
| `aiws_apps.py` / `aiws_launcher.py` | 集成应用注册表；桌面启动器（只为“已批准且运行中”的 `app.launch` 阶段启动，自己重新核对） | 不接收参数；环境白名单；限速 |
| `aiws_guest_ops.py` / `aiws_guest_boundary.py` | 受限系统服务/内核操作；客户机边界检查 | 客户机权限 ≠ 宿主权限 |
| `aiws_mcp.py` | 对外只读 MCP stdio 门面 | 不公开写工具 |
| `aiws_local_model.py` / `aiws_model_gate.py` / `aiws_model_schema.py` / `aiws_model_router.py` / `aiws_model_registry.py` | 本地模型：提议校验、懒启动与空闲卸载、受约束输出、规则→本地→官方 CLI 路由 | 离线；只提议 |
| `aiws_events.py` / `aiws_observatory.py` | 事件库与观察台汇总（token 只统计提供方上报数字） | 只读；不触发模型调用 |
| `aiws_mandate.py` / `aiws_supervisor.py` / `aiws_cli_adapters.py` / `aiws_egress_proxy.py` | 官方 CLI 一次性授权、监督与用户隔离、输出解析、域名白名单代理 | 不保存 API 密钥；预算超限即停 |
| `aiws_boot_slots.py` | 启动槽位（A/B 候选）管理 | 原型 |

新增运行时模块时**先把文件名加入 `os/runtime/MODULES`**；`test_runtime_manifest.py` 会在清单与目录不一致时失败。

## 前端（`workbench`）

| 路径 | 职责 |
| --- | --- |
| `src/os/OsWorkbench.tsx` | VS Code 风格外壳：状态、标签、侧栏内容、命令、状态栏 |
| `src/os/Shell.tsx` | 通用外壳组件：活动栏、侧栏、标签栏、面板、状态栏、命令面板 |
| `src/os/Observatory.tsx` + `useObservatoryData.ts` | 观察台；单一轮询 hook（页面隐藏时停止） |
| `src/os/FileViewer.tsx` / `BrowserView.tsx` | 文档阅读器（Markdown/CSV/JSON/图片/PDF/DOCX/沙箱 HTML）；预览浏览器（只嵌本机开发服务与沙箱 HTML） |
| `src/os/Guest*.tsx` | AI 文件管理（需审批）、任务/本地 AI、系统控制 |
| `src/os/api.ts` / `observatoryTypes.ts` | 对本地服务的唯一调用入口与类型 |
| `src/os/shell.css` / `OsWorkbench.css` | 主题变量（`--c-*`，深色默认） |
| `src/model/*.mjs` + `tests/` | 无 DOM 的纯逻辑（标签、命令、快捷键、文件树、Markdown 解析、浏览器地址校验），由 node 测试覆盖 |

## 执行路径

```text
你（自然语言）→ 观察台 →（规则 → 本地小模型）提议 → 审批 DAG → 受限工具 / 桌面启动器
                                      └ 超出本地能力且你已授权 → 官方 CLI（专用低权限用户 + 出口白名单）
所有环节 → 事件库 / 哈希链审计 → 观察台
```

## 目录维护原则
1. 新功能放进现有模块；不要为“整理目录”移动被 live-build、CI 引用的路径（改名要同步 `os/debian/build.sh`、工作流与测试）。
2. 旧资料进 `docs/history/`，不要在 `docs/` 根目录堆旧文档。
3. 不把应用层 Broker 宣称为内核隔离；不把 CI 配置宣称为 CI 已通过。
4. 每次仓库修改在 `docs/routine/YYYY-MM-DD_HHMMSS-*.md` 记录改动、验证、限制、下一步（`AGENTS.md`）。

## CI 与发行

| Workflow | 作用 |
| --- | --- |
| `aiws-os-static.yml` | Python 契约与行为测试、Shell 语法 |
| `aiws-os-image-boot.yml` | Debian live-build、QEMU、BIOS/UEFI 固件矩阵 |
| `aiws-real-model.yml` | 真实 GGUF / llama.cpp 客户机推理基线 |
| `release-preview.yml` | 构建完整测试版 ISO（含模型权重）并发布为 pre-release |

以工作流**实际成功的结论与对应提交**为准；仓库里存在工作流文件不等于已通过。
