# 2026-11-20 21:10 — Resolve Playwright ambiguous navigation selector / 交互测试歧义修复

## 中文
最新 Windows Playwright 失败并非导航不能使用：切换 English 后，侧栏「Plan Studio」与内页「Plan Studio」链接同时存在，测试采用严格定位而命中两项。现显式检查第一个同名按钮，避免把合法的双入口误当作失效。原有导航逻辑不变。
## English
The observatory's English view correctly exposes two Plan Studio buttons (sidebar and in-page cross-link). Playwright strict mode rejected the ambiguous selector. The assertion now selects the first matching accessible button.
## 证据 / Evidence
- Failing Windows run: #44739752600 (Edge selector ambiguity).
## 下一步 / Next
Rebuild on Windows, complete bilingual historical records and publish only after all automated gates pass. Real VM validation remains pending.
