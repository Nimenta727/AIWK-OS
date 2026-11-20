# 2026-11-20 22:36 · Code intelligence verified on AIWS OS static CI / 代码智能回归验证

## 中文
**本次改动：** 保存跨平台代码智能引擎本轮的可核实测试证据，并在 routine 索引记录最新开发节点；本次不改动功能代码。

**影响文件：**
- docs/routine/2026-11-20_2236-code-intelligence-ci-verified.md
- docs/routine/README.md

**验证：** GitHub Actions CI job 136340212573, workflow run https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44751486250，测试提交 b0adb1659df4a7eba414e4e9085a8c847f9fd24a 的 Linux OS 静态测试 **28/28 通过**（Python unittest / bash shell syntax）。覆盖 C#、Swift、Windows XML、XAML 类声明、依赖/引用、MCP 与安全输入规则。此 CI 是独立 Ubuntu runner 静态验证，不是 Debian 13 Live ISO 启动测试。常规 Python & Windows checks workflow 的状态需要单独核查，不能据此宣称它已通过。

**已知限制：** 静态解析器仍不能准确解析重载/泛型/扩展宏的语义，代码引用属于 unresolved-lexical 候选；没有安装 Roslyn/SourceKit-LSP，没有针对真实 Windows/macOS 工程的大样本误报/漏报基准，没有验证虚拟机内核/VM 安全。

**下一步：**
1. 获取所有 CI 的明确结果并完成失败修复。
2. 引入受控、可选的 Tree-sitter 解析器以提升语法准确度，建立正反例测试。
3. 增加 Roslyn C# / SourceKit-LSP Swift 的语义后端，独立 VM worker 与资源限制；区分 authoritative LSP evidence 和 lexical candidate。
4. 真实构建 Debian Live ISO、运行 KVM/Hyper-V 隔离验收。
5. 完成原始 MIT 与新 Apache-2.0、Debian/Linux/第三方组件的许可和源码义务审查。

## English
Archive verified 28/28 offline static tests for the cross-platform code intelligence MCP API on the exact preceding commit. Do not mistake this for a booted guest, semantic language-server verification, or Windows/macOS native compilation. Next: CI follow-up, parser/semantic engines, VM acceptance and license inventory.
