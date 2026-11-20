# 2026-11-20 22:26 · Offline C#/Swift code intelligence / 跨平台代码智能静态索引

## 中文
**修改内容：** 为 AIWS OS 增加纯 Python 标准库的代码智能模块，接入现有 MCP stdio。4 个只读工具：code.symbols（定义候选）、code.references（跨文件词法引用）、code.dependencies（.NET XML/SwiftPM/XcodeGen 清单）、code.platformApis（WPF/WinUI/interop/SwiftUI 等 API 线索）。返回位置、证据等级、truncated 和 semanticVerified=false，避免误报为完整编译器语义解析。ISO live-build 将复制新模块到 /usr/local/lib/aiws。不增添闭源二进制或强制网络调用。

**影响文件：** os/runtime/aiws_codeintel.py, os/runtime/aiws_toolplane.py, os/debian/build.sh, os/verify/test_codeintel.py, docs/AIWS_CODE_INTELLIGENCE.md, docs/AIWS_AGENT_TOOL_FABRIC.md, docs/README.md, os/README.md, README.md, 本 routine。

**验证：** 新增离线 unittest 覆盖 C#/Swift 符号、同名歧义、跨文件引用、注释/字符串屏蔽、Windows API、NuGet/MSBuild/SwiftPM、损坏 XML、符号链接和文件大小上限、MCP 端到端。提交后须在 GitHub Actions 检查实测 CI；未声称生成/启动 ISO 或执行 Roslyn/SourceKit-LSP。

**已知限制：** 无完整 AST/类型解析、重载解析、动态 manifest 执行、macOS SDK 验证、Windows 原生编译、缓存增量索引。上层 Agent 控制平面尚未移植 Linux，宿主侧隔离尚未通过攻击面验收。

**下一步：** 检查并修复 CI；用 Windows/Swift fixture 数据集测误报和漏报；单独审核并集成可选 Roslyn 与 SourceKit-LSP 后端；真实 VM 启动和安全检查；实现带权限/资源隔离的语言服务 worker，补充许可证清单。

## English
Implement a read-only cross-platform code evidence index and expose four MCP tools for C#/Swift symbols, unresolved lexical references, MSBuild/Swift dependencies and platform API usage. All results are explicitly unverified and bounded; actual Roslyn/SourceKit-LSP integration and VM tests are future work.
