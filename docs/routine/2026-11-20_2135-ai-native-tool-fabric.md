# 2026-11-20 21:35 · AI-native tool fabric / 原生 AI 工具能力集成

## 中文
**变更摘要：** 根据“AI 是软件工具主要使用者”的产品定位，增加原生 Linux 客户机工具层及实验性 MCP stdio 适配器。提供文件清单、读取、带 SHA-256 冲突保护的写入、代码字符串搜索、Git status/diff、语言探测、显式启用的测试、HTML 文本提取和通过 Debian Chromium WebDriver 的无持久会话网页快照。镜像构建时将工具层封装进入 /usr/local/lib/aiws。仅从 Debian 官方包安装 browser driver/Selenium 和 Maven，未复制第三方代码。

**影响文件：**
- os/runtime/aiws_toolplane.py, os/runtime/aiws_mcp.py
- os/debian/config/includes.chroot/usr/local/bin/aiws-toolctl
- os/debian/config/package-lists/aiws-desktop.list.chroot
- os/debian/build.sh
- os/verify/test_toolplane.py
- docs/AIWS_AGENT_TOOL_FABRIC.md, docs/README.md, os/README.md, README.md
- docs/routine/2026-11-20_2135-ai-native-tool-fabric.md

**验证：** 提交后由 GitHub Actions 静态测试 Python unittest 和 bash -n；其结果须实际检查，不以代码存在代替通过。无 Debian Live ISO 实机 Chromium 或内核验证。

**限制：** 这不是已完成 Linux AIWS Agent 编排器。MCP 目前只提供关键 stdio 方法；没有完整标准认证、LSP、系统级 Broker 或外部篡改防护审计。浏览器白名单仅是应用级约束，非网络边界。显式授权运行测试也可能执行任意客户机代码。根 LICENSE 仍为 MIT，Apache-2.0 迁移和重分发检查未完成。

**下一步：** 检查 CI → 实机镜像构建和浏览器启动 → Agent 连接 MCP → 引入 LSP/Tree-sitter → 受限系统级执行 Broker → 宿主侧网络隔离与权限审计 → SBOM/许可证。

## English
Added a guest-native, machine-callable capability layer and experimental MCP stdio gateway; bundled via live-build and covered with offline tests. Functions: scoped file read/write, code search, git, tool discovery, opt-in fixed-profile tests, local HTML and Chromium WebDriver snapshots. This is *not* a shipped Linux Agent service or an isolation proof. Next: CI and VM verification, agent integration, language intelligence, privileged broker and compliance.
