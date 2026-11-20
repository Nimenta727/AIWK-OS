# 2026-11-20 20:47 — README and release documentation / 主 README 与发行资料重构

## 中文
- 完全重组根 README，提供同步的中文与 English 产品说明、安装、测试、隐私、许可与已知限制；过时版本记录可由 Git 历史与 docs/routine 查证。
- 保留此前 README 原文到 docs/archive/README_BEFORE_V19.md，避免失去历史发行操作说明。
- 新增双语发行说明与人工/自动发布检查清单；技术文档和历史日志的双语索引稍后单独提交。
- 文档整理不改变运行代码，也不代表通过真实 Hyper-V GUI 验收。

## English
- Replaced the overgrown chronological README with aligned Chinese and English sections.
- Archived the previous README in docs/archive; added bilingual prerelease notes and acceptance gates.
- Remaining: index the entire documentation corpus and historical routine logs, verify Windows CI, and publish a prerelease with checksum.

## 下一步 / Next steps
1. Append bilingual historical capsules without altering original technical/test statements.
2. Publish documentation navigation/index and release workflow.
3. Validate the actual Windows artifact and keep manual VM gates clearly pending.
