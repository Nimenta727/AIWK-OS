# 2026-11-20 22:28 · Fix code-intelligence index extension collection

## 中文
**修改：** GitHub AIWS OS static workflow 在测试代码智能工具时报告 TypeError：字典 CODE 与集合 MANIFEST 不可直接作 | 合并。将索引扩展名检测改为 set(CODE) | MANIFEST，其他行为不变。
**涉及文件：** os/runtime/aiws_codeintel.py、本 routine。
**验证：** 本条根据真实 CI 报错定位；修复提交后需重新执行 GitHub Actions，不能预称成功。
**限制：** 新工具仍是词法/语法模式索引，尚无 Roslyn/SourceKit-LSP、ISO 实机或 OS 隔离验收。
**下一步：** 确认完整 26+ 静态测试成功，若还有失败继续修正，并更新真实 CI 结果。

## English
Fix an actual CI runtime TypeError when merging a dict with a set in the source file classifier. Revalidate on GitHub Actions; language-server and ISO acceptance remain pending.
