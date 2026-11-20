# 2026-11-20 15:09 — V1.2 后续产品路线图归档

## 目标
用户要求完整写出 Windows AI Workstation 后续开发规划。以 V1.2 当前仓库为基线，区分已验证能力和未来目标，不改动任何运行时逻辑。

## 本次变更
- 新增 docs/ROADMAP.md：产品定位、当前基线、V1.3–V2.0 分阶段路线图、架构边界、专业上游源码迁移规则、任务清单、验收门槛、风险和后续候选方向。
- 更新 README.md：在开头添加路线图入口，便于后续开发和代码审查引用。
- 新增此 docs/routine 时间日志，落实每次 GitHub 修改的可追溯要求。

## 涉及文件
- README.md
- docs/ROADMAP.md
- docs/routine/2026-11-20_1509-full-product-roadmap.md

## 审查与验证
- 核对 GitHub main 为 V1.2 基线 2ebeb1b50d601f5ab081326fddbeb06c2d6fcc3f。
- 查阅 README、ARCHITECTURE、SECURITY、PROJECT_EVIDENCE_V12、DEVELOPER_MODULES_V11 与 MODULAR_RECOMPOSITION_V1。
- GitHub 上最近的 Native Windows Desktop EXE 成功构建是 44688011400；此记录不能代替用户 Hyper-V VM 的实机 GUI 验收。
- 本次只修改 Markdown 文档，不新增执行代码，因此不声称完成了 roadmap 所列功能或运行了额外编译测试。

## 已知风险
- 各版本范围是计划，不是发布日期承诺。
- V1.2 Git 阶段检查点反映关联，不证明 AI 代码作者。
- 官方 CLI 内部调用用量、OS 沙箱隔离、实际 Hyper-V 行为仍未全部解决。

## 下一步
1. 按 ROADMAP 的 V13-01~V13-10 拆解实施优先级与测试。
2. 优先建设每 Agent 的 Git Worktree 隔离和可审查 Git 变更证据。
3. V1.4 设计应用内终端和进程生命周期，但执行前完成权限边界评审。
4. 每次后续代码变更继续写入 docs/routine，并通过 Windows CI、实机验收分别确认。


---

## 双语历史编目 / Bilingual historical capsule (2026-11-20)

- 中文：本次档案主题为 **2026-11-20 15:09 — V1.2 后续产品路线图归档**，保留此前变更、测试结果、局限和当时的下一步计划。此追加说明不重新验证历史结论。
- English: This dated record concerns **full product roadmap**. Its earlier changes, tests, caveats and next steps are preserved. This appended synopsis is not a new verification.
- [历史时间线 / Log index](README.md) · [当前发行 / Current release](../../README.md)
