# 2026-11-20 22:32 · XAML class binding and XML parser hardening / XAML 类型映射与 XML 防护

## 中文
**改动：** 为跨平台代码智能增加 WPF XAML 根节点 x:Class 候选引用，使 code.references 能关联到 C# 类型，code.platformApis 返回 WPF XAML 命名空间证据；拒绝处理带 DTD/ENTITY 声明的 MSBuild XML，避免从项目配置扩展恶意实体。
**文件：** os/runtime/aiws_codeintel.py, os/verify/test_codeintel.py, docs/AIWS_CODE_INTELLIGENCE.md, 本 routine。
**验证：** 新增 2 项覆盖 XAML class binding、XML DTD 实体拒绝；提交后运行 GitHub Actions，不预先声称通过。
**限制：** 仍属候选符号匹配；无法取代 Roslyn/XAML 编译器，不会执行项目/网络 SDK。
**下一步：** CI 检验、歧义负例数据集、接入受限 Roslyn/SourceKit-LSP、VM 实测与许可证审计。

## English
Add XAML x:Class-to-C# candidate links and WPF namespace evidence; reject DTD/entity-bearing project manifests to prevent parser expansion. New regression tests. Pending GitHub Actions; language servers and native VM validation remain future work.
