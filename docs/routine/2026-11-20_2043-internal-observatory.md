# 2026-11-20 20:43 — V1.9 internal observability / 内部执行透视

## 变更 / Changes
- 新增统一的执行透视页面：任务拓扑、五段证据链、上下文来源清单、Token 可信用量、Git 文件目录展开与 Diff。
- Added the Internal Observatory and local projection model, with explicit unknown-evidence semantics.
- 在工作台主导航加入中/英切换；更新 UI 版本为 1.9.0-preview.1。
- Added Node regression checks and Playwright navigation/language interaction coverage.

## 验证 / Verification
- 本地既有 Python 38/38；Windows UI/WPF/Edge CI 以提交后的 GitHub Actions 结果为准。
- Unknown model calls remain unknown; no unattended CLI invocation is introduced.

## 下一步 / Next
1. 完成主 README 与技术文档的中英双语目录，以及历史 routine 的双语归档摘要，保留原始记录事实。
2. 完成 Windows CI、发行说明、校验和及 GitHub Preview Release 流程。
3. 在用户 Hyper-V 虚拟机进行原生对话框、ConPTY、目录、IME 和权限操作的独立验收。
