# AIWS OS AI-native Tool Fabric / 面向 Agent 的系统工具能力层

**Status: independent guest Agent + same-UID Permission Broker + read-only MCP facade. Real firmware/GUI CI is tracked separately. This is NOT mandatory Linux isolation.**

## 中文：软件是 AI 的能力，不是窗口的堆砌

AIWS 目前采用只读 MCP stdio → systemd Agent → 独立用户态 Permission Broker → 受限工具的路径。写入（如 file.replace、systemd model service 变更）必须走 SQLite 持久 DAG 审批、进入 running 并经过独立 Broker 再执行。Broker 与 Agent 当前使用**同一个客户机 UID**，因此它是应用层故障关闭的决策点，**不是**内核强制安全边界。下一步是独立低权限 Worker UID、受保护策略和 Linux LSM/Landlock 等内核强制隔离；不把客户机 root 或宿主接口授予 Agent。

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
| file.replace | Atomic UTF-8 replacement with previous SHA-256, via approved persistent Agent DAG only | Not in MCP stdio's public read-only catalog |
| file.stat | Type, size, mtime, SHA-256 (directory: bounded tree fingerprint, refuses symlinks) | Read-only; direct Agent/Broker read path |
| file.mkdir | Create one new directory under an existing parent | Write: approved DAG only |
| file.copy | Copy one regular file (<=64MiB) to a new path with SHA-256 precondition; never overwrites | Write: approved DAG only |
| file.move | Move/rename a file or directory; fingerprint precondition; never overwrites | Write: approved DAG only |
| file.trash | Move to reversible `.aiws-trash/` inside the workspace; **there is no permanent-delete tool** | Write: approved DAG only |
| file.restore | Restore a trashed item to its original path if free and fingerprint still matches | Write: approved DAG only |
| code.search | Literal string search, line numbers, capped entries | No LSP/Tree-sitter implementation yet |
| git.inspect | status/diff, fixed git arguments, no push | Git subprocess; not a security sandbox |
| runtime.detect | Detect language/compiler/editor/browser executables | No code execution |
| runtime.test | Fixed test profiles remain in low-level prototype toolplane | Not exposed by read-only MCP or production task DAG; must be redesigned under sandboxed worker |
| browser.local_text | Extract visible-ish text from a local HTML document | No script execution |
| browser.snapshot | Experimental headless Chromium DOM snapshot in toolplane | Not exposed by read-only MCP; origin filtering alone is insufficient |

### Example: AI invokes tools using MCP stdio

Under guest user shell, set the workspace before starting the server:

    export AIWS_WORKSPACE="$HOME/my-project"
    aiws-toolctl --list

Configure an MCP client using command /usr/local/bin/aiws-toolctl with stdio transport. Its public tool list is **read-only**: initialize, ping, tools/list and tools/call use JSON-RPC 2.0 newline framing; tools/call forwards through the live guest Agent and Broker, and fails closed if those services are down. The prototype is not certified for all MCP features; there is no host management RPC.

Setting AIWS_ALLOW_EXEC no longer exposes test execution through aiws-toolctl. Read-only MCP calls require the Agent and the Broker, and all guest writes need approved persistent DAG stages. A separate shell/Python process with this UID can still bypass this application architecture: the enforced worker sandbox and host policy are future, independently tested work. See [Permission Broker threat model](AIWS_PERMISSION_BROKER.md).

### Browser is AI-controlled, not an unrestricted embedded website

Debian packages chromium, chromium-driver and python3-selenium are installed by the image recipe. The browser.snapshot tool uses a temporary headless profile, no persistent cookies, browser sandbox left enabled, and requires a configured exact-origin allowlist (AIWS_BROWSER_ALLOWED_ORIGINS). No origin allowed by default. Redirect checking is **post-navigation**, therefore origin filtering does NOT enforce confinement; a malicious redirect could access another origin before the check. A separately enforced, isolated network segment and egress controls at the **host** are mandatory before enabling an Agent-controlled browser with Internet access. Do not browse private accounts, local credential services, or untrusted host networks from a privileged guest.

### Audit is limited

The tool plane writes best-effort local metadata to ~/.local/state/aiws/toolcalls.jsonl, hashing tool arguments without saving prompts. A guest Agent can alter that file; external host-side append-only evidence is a future task, not shipped.

## English / Architecture and next steps

The agent first discovers *capabilities*, not app windows. Only read-only operations are exposed over the guest's MCP stdio facade; approved mutations are separate persisted DAG stages backed by the Agent/Broker decision path. Human-facing XFCE/Firefox/Geany remain available for inspection, but do not own execution state. Existing Windows WPF orchestration is **not** yet ported.

**Next:** add a Linux service/Agent orchestrator reusing the unified task schema; test Chromium WebDriver and language tools in a booted ISO; add LSP/Tree-sitter symbol adapters, structured build output, explicit browser navigation and user inspection surfaces; implement non-root broker + cgroup limits and host audit; install/upgrade image, repeatable ISO build and licensing/SBOM. Gate changes behind actual VM validation.

## Source architecture references
- MCP specification: https://modelcontextprotocol.io/specification/2025-11-25
- LSP: https://microsoft.github.io/language-server-protocol/
- Tree-sitter: https://github.com/tree-sitter/tree-sitter
- Playwright MCP concepts: https://playwright.dev/docs/getting-started-mcp
- OpenHands SDK concepts: https://github.com/OpenHands/software-agent-sdk
- Debian chromium-driver package: https://packages.debian.org/trixie/chromium-driver
