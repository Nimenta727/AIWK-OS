# 2026-11-22 20:00 — 模型工具箱补齐、Swift、项目预览、AIWS Code 嵌入工作台

## 背景
用户要求：把模型的工具配齐；支持 Swift；模型能在平台上构建/编译所有代码，只需检查错误并能预览；集成程序员常用工具，把程序员工作台（像 VS Code、能承载大型项目）放进来。

## 改动
- **Swift**：`build_run` 新增 swift（`swiftc -typecheck/build/run`、Swift 包 `swift build/test/run` 且固定 `--disable-automatic-resolution`）；Apple 专有框架（SwiftUI/UIKit/AppKit 等）报错时追加明确说明；`find_tool` 还会查 `/opt/swift/usr/bin`、`/usr/libexec/swift/*/bin` 等工具链目录。
- **依赖缓存**：新增每用户依赖缓存（`AIWS_DEP_CACHE`）；`build_run` 离线读取，`deps_install` 是唯一联网的一步。
- **`deps_install`**：经批准的依赖下载（go/rust/javascript/python/java/csharp），每种语言一条固定命令；只经白名单代理；npm `--ignore-scripts`、pip 只要 wheel，不运行安装脚本；没有代理就拒绝；批准类别是不可关闭的 `network`。
- **`git_commit`**：只做本地暂存与提交；无 push/pull/reset/rebase/checkout；git 加固运行（无钩子、无系统/全局配置、无编辑器/签名/外部 diff）；项目必须是自己仓库的根；新批准类别 `commit`。
- **项目预览**：`aiws_preview.py` 只读静态服务器（仅回环），`/api/v1/preview`；预览页顶部“项目预览”条。
- **AIWS Code 嵌入标签页**：`/api/v1/ide/start`（只启动服务器）与 `/api/v1/ide/session`（受 CSRF 保护，读取私有令牌文件生成地址）；`IdeView` 标签页。
- **镜像**：开发者清单新增 `mono-mcs`、`mono-runtime`、`gopls`、`rust-analyzer`、`python3-pylsp`、`clang-tidy`、`cppcheck`、`lldb`；可选 Swift 清单（`AIWS_WITH_SWIFT=1`，约 2 GB）；包仓库主机放进**默认关闭**的 `egress-registries.conf`，代理新增可选 `--allow-extra`。
- **前端**：构建页新增依赖下载/本地提交开关；总览侧栏新增“代码编辑器”；预览浏览器可由“项目预览”驱动。

## 查证（用真实 Debian 13 软件包索引核对）
Debian 13 官方源**有** `swiftlang 6.0.3-2`（安装后约 2073 MiB）、`mono-mcs`/`mono-runtime`、`gopls`、`rust-analyzer`、`python3-pylsp` 等；**没有** .NET SDK、`jdtls`、TypeScript 语言服务器。运行 `os/debian/tools/check_packages.py`：117 个包、0 个缺失。

## 验证
- Python 746 项通过（2 项跳过为既有）；前端 45 项、`tsc`、`vite build` 通过。
- 真编译器：C、C++（含 cmake）、Go、Python、Rust（rustc 与 cargo）、Java、Node 在测试里真的编译并运行；Swift、C# 本机没有工具链，只测了命令规划和“未安装”的报错。
- **真实的 pip 流程**：本地 wheel 索引 → `deps_install` 装进项目 → 离线 `build_run` 能 import；源码包被拒绝，`setup.py` 不会执行。
- **变异检查**：去掉 git 的 `core.hooksPath` 后“钩子不会运行”测试失败；去掉 `--only-binary` 后“不执行 setup.py”测试失败；均已还原。
- 预览：路径解析对 `..`、编码、反斜杠、NUL、符号链接、隐藏文件、目录列表、Host 重绑定、超大文件、空闲停止都有测试。
- 浏览器（API 用夹具模拟）：文件查看器、预览页（含真实起的预览服务器替身）、IDE 标签页（替身页面）截图人工看过；英文模式下无中文残留。

## 发现并修复的问题（含我自己造成的）
- **我之前删除 `shell.css` 时，预览浏览器和文件查看器丢了全部样式**（iframe 没有尺寸）；当时的截图没有打开这两页。这次发现后补了 `viewer.css` 并实际截图确认。
- 清单测试发现 `aiws_build_tool.py` 没写进 `MODULES`（镜像里会缺这个模块）——上一轮已修。
- 注册表主机最初加进了常开白名单，被“白名单最多 6 项”的守卫测试拦下；改成默认关闭的单独文件。
- git 工具里 NUL 检查最初写成了 `"\\x00"`（比较的是字面文字而不是空字节），已改正并验证。
- 重复软件包被“清单无重复”的测试拦下，已去重。

## 未验证 / 局限
- **AIWS Code 从未构建过**（`os/ide/README.md` 写明首次构建即验收）；它放进 iframe 后能否工作（框架策略、Webview、WebSocket）未知；我只验证了工作台这一侧。
- Swift：Debian 的 `swiftlang` 把二进制放在哪里、`swiftc` 是否在 PATH 上，我没能核实；Swift 包依赖下载不支持；Apple 框架代码不能构建。C# 没用真编译器测过。
- 依赖下载的主机清单可能不完整；各语言的下载流程里只有 pip 在测试中真实跑过。
- 专用用户隔离、防火墙、代理在真机上的行为未验证。
- 更多动作（格式化、静态检查）、模型侧的语义索引、编辑器扩展的离线打包都没做。

## 下一步
1. 在有网络的构建机上构建 AIWS Code（`os/ide/build-aiws-code.sh`），装进镜像后实测嵌入。2. 决定是否在镜像里带 Swift（+约 2 GB；CI 磁盘需评估）。3. 用你的 DeepSeek 密钥做第一次真实运行。4. 真机验证隔离与依赖下载。
