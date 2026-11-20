# 2026-11-20 21:12 — Checksummed GitHub Preview Release workflow / 预发布流程

## 中文
新增独立 .github/workflows/publish-preview.yml：只有明确的 [publish-release] main 提交或手工 workflow_dispatch 才会运行，重新验证 Node、Edge Playwright、.NET、Python 后发布 Windows ZIP 和 SHA-256；发行包包含 MIT、T3 Code 署名和双语 README/发行说明。GitHub Release 必须标为 prerelease，遇到现有 tag/Release 不覆盖。任何自动测试失败都禁止创建发行。
## English
Added a gated Windows preview-release workflow. It rebuilds and retests the full app, packages the offline UI, README and license notices, computes SHA-256 and invokes GitHub prerelease publication only after all automated checks pass.
## 当前边界 / Caveat
工作流尚未实际发布，发布结果需由后续 Actions 确认；Hyper-V GUI、原生终端及签名依然未完成。
## 下一步 / Next
Finish dated bilingual history records, validate main CI, then trigger one explicit prerelease commit. Do not claim a stable or signed release.
