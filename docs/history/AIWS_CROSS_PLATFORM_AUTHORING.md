# Cross-platform source authoring / Windows 与 macOS 项目源码编写

**Status:** AIWS OS guest tool-plane prototype, not an SDK emulator or native compiler.

## 中文

AIWS 的工具优先服务 Agent：在 Linux Guest 内直接创建、查阅、修改 Windows/macOS 应用项目，而用户可用文本编辑器查看结果。没有在 ISO 中打包 Windows/macOS、Xcode、Apple SDK 或微软闭源 IDE。

本轮实装两个 MCP stdio 工具：

- \`platform.inspect\`：对所选工作区内的项目路径进行只读扫描，识别 .sln/.csproj/.vcxproj/.xaml、Swift、.plist/.entitlements、.xcodeproj/.xcworkspace、.storyboard/.metal 等文件。基于**文件名和扩展名**给出候选平台，不自动编译、访问网络、运行项目或推断源码一定能跨平台。
- \`project.scaffold\`：在当前 workspace 内创建新的完整源码子目录，支持 \`windows-wpf\`（.NET 10 WPF csproj/App.xaml/MainWindow.xaml）和 \`macos-swiftui\`（SwiftUI 源码 + XcodeGen 的 project.yml）。已有目录名会失败，绝不覆盖原文件。需用户在客户机环境显式设置 \`AIWS_ALLOW_SCAFFOLD=1\`。

示例（从 Linux guest 的普通用户终端）：

\`\`\`bash
export AIWS_WORKSPACE="$HOME/my-projects"
AIWS_ALLOW_SCAFFOLD=1 aiws-toolctl
\`\`\`

MCP 客户端通过 \`tools/call\` 调用：

\`\`\`json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"project.scaffold","arguments":{"name":"MyWinApp","template":"windows-wpf"}}}
\`\`\`

或：

\`\`\`json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"project.scaffold","arguments":{"name":"MyMacApp","template":"macos-swiftui"}}}
\`\`\`

生成后的源代码还可使用既有 \`file.read\` / \`file.replace\`（SHA-256 冲突检查）/ \`code.search\` 继续编辑。当前支持 UTF-8 文本；二进制 asset、签名证书、Xcode 私有格式的完整可视化编辑尚未实现。

**Windows:** 可编辑 C#/XAML 和项目清单，原生 WPF 运行与验证需要 Windows。Linux 上的源码编辑 ≠ 完成 Windows 构建。

**macOS:** SwiftUI 源码和 XcodeGen 配置可在 Linux 生成，Apple 平台专属 SDK、签名、公证、Mac 原生 UI 预览/测试需 macOS/Xcode。项目提供一个 XcodeGen 配置而非生成的 .xcodeproj；XcodeGen 由使用者自行在 Mac 安装。开源 Swift 在 Linux 可运行的模块不代表 SwiftUI 原生可用。

**安全/合规：** 生成器无需宿主权限，不运行新工程、不下载 SDK、不假冒代码签名。运行 MCP 的普通用户的读写权限是客户机权限，不构成 OS 沙箱。任意用户选择的已有源码仍属于用户，生成器不会改写。源文件是 AIWS 原创模板，未复制微软或苹果闭源代码。后续 Windows/macOS 的交叉构建、远程受控测试和语言服务器需另外审查许可证与权限。

## English

AIWS OS can **author Windows/macOS source projects from Linux**. \`platform.inspect\` scans project conventions only; \`project.scaffold\` generates brand-new Windows WPF or macOS SwiftUI + XcodeGen source trees with explicit opt-in and no overwrite. Text editing, code search and Git are available through existing MCP tools. No proprietary SDK, Xcode, Windows runtime or compiled program is bundled. Native build, previews and signing remain on the corresponding OS. The Linux tool plane is still not the full port of the Windows AIWS orchestration daemon.

## References
- [Microsoft WPF](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/overview)
- [Microsoft .NET Desktop project properties](https://learn.microsoft.com/en-us/dotnet/core/project-sdk/msbuild-props-desktop)
- [Swift Linux support](https://www.swift.org/platform-support/)
- [Apple Xcode development](https://developer.apple.com/documentation/xcode)
- [XcodeGen project specifications](https://github.com/yonaskolb/XcodeGen/blob/master/Docs/ProjectSpec.md)
