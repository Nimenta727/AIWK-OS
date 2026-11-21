# 代码结构与模块职责 / Codebase map

**适用范围：** 当前 main 工作树。这里描述实际源码归属，不把设计目标当成已实现功能。

```text
AIWK-OS/
├── README.md                   # 当前产品入口（Windows + Linux）
├── AGENTS.md                   # 修改仓库和 routine 记录规则
├── LICENSE                     # 当前仓库 MIT 许可证
├── desktop/
│   ├── AIWorkstation.Desktop/  # Windows WPF/WebView2 原生宿主
│   ├── AIWorkstation.Core/     # Windows 本地任务/计划/执行控制
│   ├── AIWorkstation.Core.SmokeTests/
│   └── AIWorkstation.Frontend/ # 共用 React UI；src/os 为 Linux 模式
├── os/
│   ├── README.md               # Linux 系统构建入口
│   ├── runtime/                # 客户机 Python Agent、Broker、工具、任务
│   ├── debian/                 # live-build、chroot、systemd、Shell、ISO
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
