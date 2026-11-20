# AIWS OS AI-native Tool Fabric / 面向 Agent 的系统工具能力层

**Status: implemented guest-local tool-plane bootstrap; OS image build and live browser smoke still pending.**

## 中文：软件是 AI 的能力，不是窗口的堆砌

现有桌面工具必须通过结构化接口成为 Agent 能够理解和调用的功能。AIWS OS 采用两层：
- **普通权限工具层（本次已提交）**：MCP stdio 原型，直接读取/变更指定工作区、搜索源代码、Git 只读检查、编译环境发现、可选测试、离线 HTML 文本提取、受限制的 Chromium WebDriver 页面快照。
- **未来权限层**：Linux Agent 控制器、OS Broker（一次性批准、capability、审计、可撤销）、systemd/cgroup v2/Landlock 与内核证据。Broker 必须独立于不可信网页；客户机 root 仍是最高客户机权限。上层模型与工具层隔离，宿主 VM 安全单独实现。

本项目没有复制 OpenHands、Playwright、Tree-sitter、语言服务器或 Linux 内核源码。我们通过标准 CLI、Debian 系统包和接口调用其能力。第三方程序仍保留原许可证（例如 Chromium 项目、Selenium、Debian 用户态包各有相应协议），不能由项目的 Apache-2.0 目标覆盖。

## 跨平台源码编辑 / Cross-platform source authoring

扩展 `platform.inspect`（Windows/macOS/Swift 项目只读识别）和 `project.scaffold`（新建 Windows WPF 与 macOS SwiftUI/XcodeGen 模板，需 `AIWS_ALLOW_SCAFFOLD=1`，不覆盖已有目录），详情见 [专项文档](AIWS_CROSS_PLATFORM_AUTHORING.md)。这不是 Windows/macOS 的原生构建或仿真。

## 跨平台代码智能索引 / Cross-platform code intelligence

新增只读 MCP 工具 `code.symbols`、`code.references`、`code.dependencies`、`code.platformApis`，将 C#/Swift 的定义候选、跨文件词法引用、MSBuild/SwiftPM 依赖及平台 API 使用标记成证据对象。**尚无 Roslyn/SourceKit-LSP 语义校验**；详情见 [专项说明](AIWS_CODE_INTELLIGENCE.md)。

## 本次实装 / Implemented

| Interface | Actual operation | Boundary |
| --- | --- | --- |
| workspace.tree | Bounded source inventory; skips symlinks and large generated directories | Read-only |
| file.read | Bounded UTF-8 text + SHA-256 | Workspace relative path |
| file.replace | Atomic UTF-8 file replacement; caller must supply previous SHA-256 | Writes guest workspace; no root elevation |
| code.search | Literal string search, line numbers, capped entries | No LSP/Tree-sitter implementation yet |
| git.inspect | status/diff, fixed git arguments, no push | Git subprocess; not a security sandbox |
| runtime.detect | Detect language/compiler/editor/browser executables | No code execution |
| runtime.test | Fixed test profiles for Python/Node/Go/Rust/Java/C++ | Requires AIWS_ALLOW_EXEC=1; test code may execute arbitrary guest actions |
| browser.local_text | Extract visible-ish text from a local HTML document | No script execution |
| browser.snapshot | Chromium WebDriver headless DOM text snapshot | Exact origin allowlist; independent host network isolation required |

### Example: AI invokes tools using MCP stdio

Under guest user shell, set the workspace before starting the server:

    export AIWS_WORKSPACE="$HOME/my-project"
    aiws-toolctl --list

Configure an MCP client using command /usr/local/bin/aiws-toolctl with stdio transport and AIWS_WORKSPACE set to a specific existing project directory. The implementation supports initialize, ping, tools/list and tools/call with protocol version 2025-11-25; not a certified implementation of every current MCP feature. Calls are JSON-RPC 2.0 newline-framed. AIWS provides no HTTP listener or host management RPC.

For execution of fixed project test profiles, the user must explicitly opt in from the guest shell:

    AIWS_ALLOW_EXEC=1 AIWS_WORKSPACE="$HOME/my-project" aiws-toolctl

This toggle is a usability gate, **not a security boundary**: an Agent with ordinary guest shell access can run its own commands. Future privileged operations require a separate OS-level broker and stronger attestation.

### Browser is AI-controlled, not an unrestricted embedded website

Debian packages chromium, chromium-driver and python3-selenium are installed by the image recipe. The browser.snapshot tool uses a temporary headless profile, no persistent cookies, browser sandbox left enabled, and requires a configured exact-origin allowlist (AIWS_BROWSER_ALLOWED_ORIGINS). No origin allowed by default. Redirect checking is **post-navigation**, therefore origin filtering does NOT enforce confinement; a malicious redirect could access another origin before the check. A separately enforced, isolated network segment and egress controls at the **host** are mandatory before enabling an Agent-controlled browser with Internet access. Do not browse private accounts, local credential services, or untrusted host networks from a privileged guest.

### Audit is limited

The tool plane writes best-effort local metadata to ~/.local/state/aiws/toolcalls.jsonl, hashing tool arguments without saving prompts. A guest Agent can alter that file; external host-side append-only evidence is a future task, not shipped.

## English / Architecture and next steps

The agent first discovers *capabilities*, not app windows. Read/write/search/Git/test and browser data are offered as small, typed tools over an experimental MCP stdio adapter. Human-facing XFCE/Firefox/Geany remain available for inspection, but do not own execution state. Existing Windows WPF orchestration is **not** yet ported.

**Next:** add a Linux service/Agent orchestrator reusing the unified task schema; test Chromium WebDriver and language tools in a booted ISO; add LSP/Tree-sitter symbol adapters, structured build output, explicit browser navigation and user inspection surfaces; implement non-root broker + cgroup limits and host audit; install/upgrade image, repeatable ISO build and licensing/SBOM. Gate changes behind actual VM validation.

## Source architecture references
- MCP specification: https://modelcontextprotocol.io/specification/2025-11-25
- LSP: https://microsoft.github.io/language-server-protocol/
- Tree-sitter: https://github.com/tree-sitter/tree-sitter
- Playwright MCP concepts: https://playwright.dev/docs/getting-started-mcp
- OpenHands SDK concepts: https://github.com/OpenHands/software-agent-sdk
- Debian chromium-driver package: https://packages.debian.org/trixie/chromium-driver
