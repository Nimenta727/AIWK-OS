# 程序员工作台与模型工具箱

**English summary.** The programmer's workbench is **AIWS Code** (our own build of the VS Code open-source core), now embedded as a tab; the cloud agent's toolbox is complete for building and checking code in nine languages. What was verified, and what could not be, is listed per item below.

## 1. 给模型的工具箱（DeepSeek 运行器）
| 工具 | 作用 | 批准 | 需要隔离 |
| --- | --- | --- | --- |
| `workspace_tree` `file_read` `file_stat` `code_search` `doc_text` `git_inspect` `ext_rg` `ext_jq` `ext_gitlog` `tools_list` | 读代码、搜索、看变更 | 否 | 否 |
| `file_replace` `file_mkdir` `file_copy` `file_move` | 写文件（限定在项目内） | 可选“每次先问” | 否 |
| `file_trash` `file_restore` | 删除（进回收站） | **每次** | 否 |
| `plan_propose` `plan_update` `agent_spawn` | 结构化计划（等你批准）、子智能体 | 计划需批准 | 否 |
| **`build_run`** | 检查/编译/测试/运行：C、C++、Go、Python、Rust、C#、Java、JavaScript、**Swift** | 可选“每次先问” | **是** |
| **`deps_install`** | 下载依赖进缓存（go.mod、Cargo.toml、package.json、requirements.txt、pom.xml、.csproj） | **每次，无法关闭**（联网） | **是** |
| **`git_commit`** | 本地暂存并提交（没有 push/pull/reset/rebase/checkout） | 可选“每次先问” | 否 |

所有“运行程序”类工具默认关闭，只在构建通道使用专用低权限用户时开放（原因见 `docs/AIWS_DEEPSEEK.md` 第 8 节）。

## 2. Swift（如实说明）
- **能做**：标准库 + Foundation 的命令行程序、服务端程序、跨平台库；`swiftc -typecheck` 检查、`swiftc` 编译、`swift build/test/run`（Swift 包，固定 `--disable-automatic-resolution`，不联网拉包）。
- **不能做**：SwiftUI、UIKit、AppKit、Cocoa、Combine 等 Apple 专有框架——它们随 Xcode 的 SDK 提供，Linux 上没有。编译这类代码时输出会追加一句明确说明（不是代码的错），见 `hint_for()`。macOS/iOS 应用只能在 Mac 上构建。
- **工具链来源**：Debian 13 官方源有 `swiftlang 6.0.3-2`（已对真实索引核对）。**安装后约 2 GB**，所以做成可选：`AIWS_WITH_SWIFT=1 sudo ./os/debian/build.sh`。
- **未验证**：本环境没有 Swift，只测了命令规划与“未安装”的报错；Debian 把二进制放在哪个目录我也没能核实，所以 `find_tool` 同时查 PATH、`/opt/swift/usr/bin` 和 `/usr/libexec/swift/*/bin`；Swift 包的依赖（来自 git 主机）目前不支持下载。

## 3. C#
Debian 官方源没有 .NET SDK，但有 Mono（`mono-mcs` 编译器、`mono-runtime`，已核对并加入开发者清单）。单文件 C# 用 `mcs`/`mono`；有 `dotnet` 时优先用 `dotnet build/test/run`。**未用真实编译器验证**（本环境两者都没有）。

## 4. 项目预览
「内置浏览器」页顶部新增“项目预览”：选一个文件夹（可加子文件夹，如 `dist`）→ 启动一个**只读的静态服务器**（仅 127.0.0.1）并在下面的预览里打开。
- 防护（均有测试）：只 GET/HEAD、没有目录列表；`..`、编码的点、反斜杠、NUL、符号链接都拒绝；以 `.` 开头的文件/文件夹（`.git`、`.env`）永不提供；Host 头必须是自己的回环地址（防 DNS 重绑定）；不缓存、不嗅探、不发 referrer；HTML 带只允许同源的 CSP；空闲 15 分钟自动停止；同时只有一个预览。
- 预览的是**网页类产物**；命令行程序的“预览”就是 `build_run` 的运行输出。图形界面程序（Qt/GTK 窗口）没有预览。

## 5. 代码编辑器（AIWS Code）与大型项目
- 你要的“像 VS Code、能承载大型项目”的工作台就是 **AIWS Code**：用 VS Code 开源核心自己构建的网页版，大型项目的索引、搜索、语言服务、终端、调试、扩展都由它承担。现在作为**标签页嵌进工作台**（可选文件夹、重新加载、在独立窗口打开）；访问令牌由私有文件读取，经受 CSRF 保护的接口生成地址，只在回环地址上运行。
- 我们自己的“文件”侧栏是**轻量浏览器**，列表有上限，**不是**为大型项目设计的；大项目请用编辑器标签页。
- 镜像里新增的语言服务与分析器：`gopls`、`rust-analyzer`、`python3-pylsp`、`clang-tidy`、`cppcheck`、`universal-ctags`、`lldb`（已核对存在）。它们要通过扩展接到编辑器上才会生效，扩展的离线打包还没做。
- **未验证（最重要）**：AIWS Code 本身**还没有在任何环境里构建过**（`os/ide/README.md` 写明首次构建就是验收）；它被嵌入 iframe 后能否正常工作（框架策略、Webview、WebSocket）也没验证——我用一个替身页面验证了工作台这一侧的嵌入与沙箱属性，真编辑器需要构建后实测。

## 6. 依赖下载的出口白名单（默认关闭，需你主动启用）
- 常开的白名单仍只有云端模型的接口（含 `api.deepseek.com`），**保持最小**。包仓库放在单独的 `/etc/aiws/egress-registries.conf`（镜像里自带，但不生效）。
- 启用：`sudo cp /etc/aiws/egress-registries.conf /etc/aiws/egress-extra.conf && sudo systemctl restart aiws-egress-proxy`；复制前删掉用不到的语言，主机越少越好。文件不存在就什么也不加；文件格式有错则代理拒绝启动，不会只应用一半。
- 为什么默认关：代理只能限制流量**去哪里**，不能限制**带什么**；每多一个放行的主机，就多一个能夹带数据的地方（比如放在 URL 里）。
- 清单内容：`proxy.golang.org`、`sum.golang.org`、`index.crates.io`、`static.crates.io`、`crates.io`、`registry.npmjs.org`、`pypi.org`、`files.pythonhosted.org`、`repo.maven.apache.org`、`repo1.maven.org`、`api.nuget.org`。**未验证**：真实运行可能还需要别的主机（CDN、Maven 插件仓库）。
- 依赖安装只下载、不运行安装脚本（npm `--ignore-scripts`、pip 只要 wheel）；**依赖名来自模型写的清单文件**，所以建议批准前在“变更审查”里看一眼清单的改动。

## 7. 没做 / 局限
- 按语言的格式化、静态检查等“更多动作”还没有；目前是 check/build/test/run。
- 大型项目的**模型侧**能力靠 `code_search`（ripgrep）+ 有上限的 `workspace_tree`，没有语义索引。
- 编辑器里的 AI 功能被有意关闭（`chat.disableAIFeatures`）；模型通过我们的运行器工作，而不是编辑器里的插件。
- Swift 工具链、AIWS Code、真机上的隔离运行，都需要在真实环境里验证。
