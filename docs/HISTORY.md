# 历史版本与 Git 保留 / Historical versions

当前 README 和 [文档中心](README.md) 是最新工程入口。**旧版本不再追加到 README 末尾**；原有 README、源码和设计稿已由 Git 提交对象保留，不需要在工作树中复制多个 `README-old`。

## Git 版本快照

- [查看提交历史](https://github.com/Nimenta727/AIWK-OS/commits/main/)
- [早期 Windows + Linux 工程整合提交](https://github.com/Nimenta727/AIWK-OS/commit/ffc39eaf29e4755ec5fb65a0a6d260d1d00f24e6) — 本次文档清理前的工作树状态，包含旧版冗长 README。
- [查看该提交的旧 README](https://github.com/Nimenta727/AIWK-OS/blob/ffc39eaf29e4755ec5fb65a0a6d260d1d00f24e6/README.md)
- [按时间记录的工程修改](routine/README.md) — 每次提交的改动、测试、遗留问题、下一步。

## 历史设计资料（仅作版本参考）

以下文档仍保留原路径，避免打断已有内部交叉引用。它们**不再是当前产品功能清单**：

- Windows v0.x / v1.x： [V03_OPERATIONS](V03_OPERATIONS.md)、[EXECUTION_BASE_REVIEW_V07](EXECUTION_BASE_REVIEW_V07.md)、[DEVELOPER_MODULES_V11](DEVELOPER_MODULES_V11.md)、[IMPLEMENTATION_V13_V16](IMPLEMENTATION_V13_V16.md)、[EXECUTION_ATLAS_V17](EXECUTION_ATLAS_V17.md)、[PLAN_STUDIO_V171](PLAN_STUDIO_V171.md)、[UNIFIED_ORCHESTRATION_V18](UNIFIED_ORCHESTRATION_V18.md)、[UI_STUDIO_V181](UI_STUDIO_V181.md)、[INTERNAL_OBSERVATORY_V19](INTERNAL_OBSERVATORY_V19.md)。
- Windows 旧方案与评估： [ARCHITECTURE](ARCHITECTURE.md)、[PROFESSIONAL_FRONTENDS](PROFESSIONAL_FRONTENDS.md)、[UPSTREAM_MIGRATION](UPSTREAM_MIGRATION.md)、[MODULAR_RECOMPOSITION_V1](MODULAR_RECOMPOSITION_V1.md)、[PROJECT_EVIDENCE_V12](PROJECT_EVIDENCE_V12.md)、[TOKEN_EFFICIENCY_V172](TOKEN_EFFICIENCY_V172.md)。
- 已有归档： [docs/archive](archive/README_BEFORE_V19.md)。

如果将来确实需要从当前工作树删除不再引用的旧文件，先运行文档链接检查并将删除清单写入 routine；Git 历史始终保留内容。**不重写 Git 历史，不强推覆盖旧提交。**

**English:** Current docs are the source of truth for the latest engineering status. Versioned notes are historical snapshots; Git commits preserve earlier README and source versions without duplicating them in the live tree.
