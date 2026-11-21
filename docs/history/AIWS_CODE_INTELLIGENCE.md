# AIWS OS Cross-platform Code Intelligence / 跨平台代码智能引擎

**2026-11-20 | State: read-only, offline index MVP. Not a semantic LSP/compiler or production IDE.**

## 中文 — 目标与本轮实现

系统中工具首先服务于 Agent，而非要求 AI 通过窗口手动点击：将 Windows C#/WPF/WinUI 和 Swift/SwiftUI 代码与项目结构映射成可被 Agent 查询的**证据对象**。它直接复用当前 \`AIWS_WORKSPACE\`、MCP stdio、只读文件权限边界和镜像打包流程。

本轮为纯 Python 标准库的 **静态候选索引**，没有编译任何目标平台工程、执行不可信 MSBuild/Swift manifest、下载 NuGet/Swift 包或访问专有 SDK。

| MCP tool | Available behavior | Precision |
| --- | --- | --- |
| \`code.symbols\` | C# namespace/class/struct/record/interface/enum/显式访问修饰的方法；Swift class/struct/enum/protocol/actor/extension/typealias/func/var/let | 基于词法/语法模式，未执行 Roslyn 或 Swift 编译器 |
| \`code.references\` | 对某符号搜索不同源码文件的标识符出现位置，同时返回定义候选 | 未做完整作用域解析，同名/重载会标明 ambiguous；引用是 unresolved-lexical |
| \`code.dependencies\` | MSBuild XML ProjectReference、PackageReference、FrameworkReference、PackageVersion、Import 与 TFM、UseWPF；Swift Package.swift 中**字面量** .package/.product 和 Package.resolved pin；XcodeGen platform 提示 | 不执行条件、变量展开、依赖解析或宏 |
| \`code.platformApis\` | WPF、WinUI/UWP、Interop 和 SwiftUI、AppKit、UIKit 等命名空间/模块及典型 SwiftUI 标识符证据 | 只确认源码中出现该模式，不确认 API 存在或目标 SDK 可用 |

补强：识别 WPF XAML 根元素的 x:Class，映射到 C# 类型名称的候选引用；对 .csproj 的 XML DTD/实体声明直接拒绝，不展开外部资源。这些结果仍非编译器语义验证。

每条符号/引用/API 包含工作区相对文件路径与行列位置，结果有 \`confidence\`、\`semanticVerified=false\`、\`truncated\` 与 \`issues\` 字段。索引每次调用重新从文件读取，避免把旧文件状态伪装成最新；单次最多检查 320 个小于 192 KiB 的候选文件，截断时不提供完整性承诺。按目录忽略 .git、build、obj、node_modules 和链接，不访问工作区之外的路径。

**重要局限：** 这不是 AST 解析器，也不能声称准确理解任意 C# 泛型、Swift 宏、混合语言工程、动态依赖、方法重载、条件编译或代码生成。没有 Roslyn/SourceKit-LSP 的条件下，定义和引用均只能作为候选提示，不用于自动重命名或破坏性重构。

### Agent 侧使用 / MCP

在 Linux 客户机以普通用户提供工作目录，启动 \`aiws-toolctl\`（MCP stdio）：

\`\`\`bash
AIWS_WORKSPACE="$HOME/projects/my-app" aiws-toolctl
\`\`\`

典型请求：

\`\`\`json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"code.symbols","arguments":{"query":"ContentView"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"code.references","arguments":{"symbol":"ContentView"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"code.dependencies","arguments":{}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"code.platformApis","arguments":{}}}
\`\`\`

这几个工具**只读**，不会改变文件或运行构建任务。AI 可结合现有 \`file.read\` / 带 SHA-256 冲突保护的 \`file.replace\` 继续修改源码。代码修改及执行均应有用户授权和版本审查。

## 下一阶段：接入真正语义后端（尚未实现）

1. **Roslyn C# LSP**：在 Linux 普通用户下，通过安装者明确选择和审计的 C# 语言服务提供 definitions/references/hover/diagnostics，语义证据与静态候选保持分层，不把二者混用。
2. **SourceKit-LSP**：Swift for Linux 工具链可提供语言服务；对于 SwiftUI/AppKit/macOS SDK 没有 Linux SDK 时，保持“无法完整验证”。
3. **依赖图**：MSBuild 条件评估、SwiftPM manifest 解析和项目引用图采用显式受限的工具链调用；项目脚本/构建目标可能执行代码，必须使用独立权限/资源配额限制的 VM worker，不能在 OS 控制守护进程中直接执行。
4. **类型与引用质量**：引入解析树和 incremental index（例如 Tree-sitter 语法树 + Roslyn/SourceKit-LSP），测试重载/混合命名空间/宏/大仓库，精确度必须用带标准答案的数据集验证。
5. **GUI 人工审查**：将证据链接到 OS 的只读源码阅读器/项目图谱；保持 AI 调用优先、人类按需查看。
6. **宿主隔离**：Linux 客户机 root 不等于宿主 root；任何深度语义服务可能执行加载钩子，默认不可信。真实 ISO 构建、KVM/Hyper-V 启动与隔离测试未完成。

## English

The first code intelligence implementation is a **bounded, read-only, no-dependency lexical evidence index** for C# and Swift plus MSBuild/SwiftPM/XcodeGen manifests and common Windows/Apple UI API hints. It produces MCP-callable findings with source locations, incomplete-result signals and explicit unverified confidence. It does **not** replace Roslyn/SourceKit-LSP or validate Windows/macOS binaries.

### References / 参考
- [Roslyn Language Server](https://github.com/dotnet/roslyn/tree/main/src/LanguageServer)
- [SourceKit-LSP](https://github.com/swiftlang/sourcekit-lsp)
- [MSBuild ProjectReference](https://github.com/dotnet/msbuild/blob/main/documentation/ProjectReference-Protocol.md)
- [NuGet PackageReference](https://learn.microsoft.com/en-us/nuget/consume-packages/package-references-in-project-files)
- [Swift PackageDescription](https://developer.apple.com/documentation/packagedescription)
