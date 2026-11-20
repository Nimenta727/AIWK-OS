# 2026-11-20 22:07 · AIWS OS cross-platform source authoring / Windows/macOS 源码工程

## 中文
**变更摘要：** 新增跨平台源码项目分析器和生成器，接入现有 Agent MCP stdio 工具接口。支持只读识别 Windows .sln/.csproj/.xaml 与 macOS .swift/.plist/.xcodeproj 等文件，支持显式开启后不覆盖原有项目地生成 Windows WPF 或 macOS SwiftUI + XcodeGen 工程。扩充 runtime.detect 对 dotnet/swift/sourcekit-lsp/xcodegen 的探测，调整 Debian ISO 构建脚本复制新模块，增加测试和双语文档入口。

**文件列表：** os/runtime/aiws_crossplatform.py, os/runtime/aiws_toolplane.py, os/debian/build.sh, os/verify/test_crossplatform.py, docs/AIWS_CROSS_PLATFORM_AUTHORING.md, docs/AIWS_AGENT_TOOL_FABRIC.md, docs/README.md, os/README.md, README.md, 本 routine。

**验证：** 新增 7 项 unittest 静态/行为覆盖（MCP 声明/调用、模板文件、Windows XML、macOS SwiftUI/XcodeGen、已存在目录保护、未启用拒绝、源工程识别）。以提交后的 GitHub Actions 输出为准；Linux ISO、Windows/Mac 原生编译、XcodeGen 真实转换、Hyper-V/KVM 安全边界并未验收。

**已知问题：** 文件识别仅凭路径后缀，可能有误报；不处理二进制资源；生成 .xcodeproj 依赖 Mac 的 XcodeGen；没有 Apple/Windows SDK；跨平台语言服务器和真正 Linux Agent controller 尚待实现。

**下一步：** 核对 Actions 绿色 → 构建/启动 ISO，验证用户点击与 MCP 连通 → 引入 Windows/MSBuild 与 Swift SourceKit-LSP 只读静态索引 → 在隔离 Windows/macOS 实机上进行构建测试 → 许可证与镜像发行审计。

## English
Add Linux-guest source authoring for Windows WPF and macOS SwiftUI via agent-callable MCP tools, plus safe platform scanning, no-overwrite scaffold, tests and docs. It does not install proprietary OS SDKs, compile the project or simulate the native desktop. CI and actual guest/client OS validation are separate gates.
