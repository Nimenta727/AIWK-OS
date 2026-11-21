# 代码结构与模块职责 / Codebase map

**适用范围：** 当前 main 工作树。这里描述实际源码归属，不把设计目标当成已实现功能。

```text
AIWK-OS/
├── README.md                   # 产品入口与系统定位
├── CHANGELOG.md                # 版本变更（预览语义）
├── AGENTS.md                   # 修改仓库和 routine 记录规则
├── LICENSE                     # 当前仓库 Apache-2.0 许可证
├── desktop/
│   ├── AIWorkstation.Desktop/  # Windows WPF/WebView2 原生宿主
│   ├── AIWorkstation.Core/     # Windows 本地任务/计划/执行控制
│   ├── AIWorkstation.Core.SmokeTests/
│   └── AIWorkstation.Frontend/ # 共用 React UI；src/os 为 Linux 模式
├── os/
│   ├── README.md               # Linux 系统构建入口
│   ├── runtime/                # 客户机 Python Agent、Broker、工具、任务；MODULES = 装入镜像的模块清单
│   ├── debian/                 # live-build、软件包清单（desktop / devtools）、systemd、Shell、ISO
│   ├── ide/                    # AIWS Code（Code - OSS 重新品牌化）构建配方、补丁、品牌、NOTICE
│   ├── builder/                # 官方 CLI 构建通道的隔离配置与自检
│   ├── platforms/nixos/       # 实验性声明式配方
│   ├── model/                 # llama.cpp 运行器、CI held-out、训练规范
│   ├── kernel/                # 内核目标选项和固件/AB 启动诊断
│   ├── host/                  # 无宿主共享的 QEMU 启动脚本
│   └── verify/                # 静态契约与客户机验证
├── aiws/                       # 旧 Python 控制平面；兼容/回归用途
├── app.py                      # 旧 Python 应用入口
├── web/                        # 旧 Python 前端资源
├── tests/                      # 旧 Python 控制平面回归
├── scripts/                    # Windows 构建、打包、Hyper-V 检查
├── .github/workflows/          # Windows/OS/model/firmware CI
├── third_party/                # 第三方署名/参考
└── docs/
    ├── README.md               # 当前文档导航
    ├── CODEBASE_MAP.md         # 本文件
    ├── HISTORY.md              # 版本资料与 Git 历史入口
    ├── AIWS_*                  # 系统设计、约束、验收
    ├── archive/                # 既有历史归档
    └── routine/                # 按时间记录每次改动和下一步
```

## Linux runtime 的职责划分

| 文件 | 职责 | 约束 |
| --- | --- | --- |
| `aiws_workbench.py` | 仅客户机 localhost HTTP、React 静态资源和任务 UI API | 不直接获得宿主虚拟机控制权 |
| `aiws_agent_service.py` | systemd 用户 Agent，持久 DAG 调度、工具执行入口 | 调用 Broker，不能以 UI 布尔值替代审批 |
| `aiws_permission_broker.py` | 独立同 UID UNIX Socket 策略决策、SQLite 阶段校验和单次授权账本 | **不是** Linux 强制访问控制 |
| `aiws_tasks.py` | SQLite DAG、状态转换、审批、审计 | 历史导入不能直接变成可执行阶段 |
| `aiws_guest_ops.py` | 受限的客户机系统服务/内核操作 | 客户机权限不等于宿主权限 |
| `aiws_toolplane.py` | 工具清单与低层工具实现 | 不是独立安全沙箱 |
| `aiws_mcp.py` | 公开只读 MCP stdio 门面 | 工具调用转交 Agent/Broker，不公开写工具 |
| `aiws_local_model.py` | 离线结构化建议、显式拒绝协议 | 模型不能直接执行工具 |
| `aiws_windows_compat.py` | Windows 任务历史/证据的受界只读导入 | 旧审批不继承 |
| `aiws_observatory.py` / `aiws_events.py` | 观察台汇总与事件库（token 只统计提供方上报数字） | 只读；不触发模型调用 |
| `aiws_model_gate.py` / `aiws_model_schema.py` / `aiws_model_router.py` | 本地模型的懒启动与空闲卸载、受约束输出、规则→本地→官方 CLI 路由 | 本地模型离线；只提议 |
| `aiws_mandate.py` / `aiws_supervisor.py` / `aiws_cli_adapters.py` | 一次性授权、官方 CLI 监督与用户隔离、输出解析 | 不保存 API 密钥；预算超限即停止 |
| `aiws_egress_proxy.py` | 构建通道的域名白名单 CONNECT 代理 | 只绑定 127.0.0.1，拒绝 IP 字面量和非公网地址 |
| `aiws_workbench.py`（IDE 部分） | `/api/v1/ide` 与 `/ide/open`：固定命令、白名单环境、限速 | 不接收任何参数 |

新增运行时模块时，**先把文件名加入 `os/runtime/MODULES`**；`test_runtime_manifest.py` 会在清单与目录不一致时失败。

## 前端（`desktop/AIWorkstation.Frontend`）

| 路径 | 职责 |
| --- | --- |
| `src/os/OsWorkbench.tsx` | Linux 模式的 VS Code 风格外壳：状态、标签、侧栏内容、命令、状态栏 |
| `src/os/Shell.tsx` | 通用外壳组件：活动栏、侧栏、标签栏、面板、状态栏、命令面板 |
| `src/os/Observatory.tsx` + `useObservatoryData.ts` | 观察台视图；单一轮询 hook（页面隐藏时停止） |
| `src/os/FileViewer.tsx` / `GuestFiles.tsx` / `GuestTaskStudio.tsx` / `GuestSystemConsole.tsx` | 文件查看、AI 文件管理（需审批）、任务/本地 AI、系统控制 |
| `src/os/api.ts` / `observatoryTypes.ts` | 对 guest 本地服务的唯一调用入口与响应类型 |
| `src/os/shell.css` / `OsWorkbench.css` | 主题变量（`--c-*`，深色默认）与布局；旧样式颜色已转为变量 |
| `src/model/*.mjs` | 无 DOM 的纯逻辑（标签、命令过滤、快捷键、偏好、文件树等），由 `tests/*.test.mjs` 覆盖 |

## 主要执行路径 / Execution paths

```text
Windows:
WPF .NET Desktop → WebView2 React → Windows Core → Tasks / CLI / Git

Linux:
Openbox + XFCE Shell → Chromium React app
  → guest localhost Workbench → private Agent UNIX socket
  → private Broker UNIX socket → SQLite running stage check
  → allowlisted guest tool → durable audit

Optional model:
GGUF / llama.cpp → JSON suggestion or explicit refusal
  → validated non-executable proposal → user-reviewed DAG

Historical import:
Windows JSON → bounded read-only mapping → SQLite audit/evidence
  → never inherit Windows execution approval
```

## 目录维护原则

1. **不要为整理目录而直接移动 Python 模块、systemd 服务路径或 React import。** 这些路径已被 live-build、CI 和打包脚本引用；迁移需要同步引用并验证真实镜像。
2. 新功能按责任域放入现有模块；`docs/` 只保留一个当前导航，旧版本事实写入 Git 历史或版本化资料。
3. 保留 `aiws/` 和 `web/` 的旧版回归用途，不把它们错误称为 Linux 运行时。
4. 不把原型的同 UID Broker 宣称为内核隔离；不把 CI 配置宣称为 CI 已通过。
5. 每次仓库修改在 `docs/routine/YYYY-MM-DD_HHMMSS-*.md` 记录改动、验证、限制、下一步。

## CI 分工

| Workflow | 验证 |
| --- | --- |
| `aiws-os-static.yml` | Python OS 契约、Shell 语法、Broker/MCP 测试 |
| `aiws-os-image-boot.yml` | Debian live-build、QEMU、BIOS/UEFI 固件矩阵、NixOS 配方 |
| `aiws-real-model.yml` | 真实 GGUF/llama.cpp 客户机推理及指标 |
| `native-desktop.yml` | Windows WPF EXE 和 UI |
| `python-windows.yml` | Python 与 Windows 跨平台回归 |

以实际 workflow 的成功结论和对应 SHA 为准，不能仅凭存在工作流文件声称验收通过。
