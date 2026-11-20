# 2026-11-20 20:59 — Browser selector validation / 浏览器测试定位修复

## 中文
V1.9 Windows CI 的前端构建成功，Edge 浏览器点击用例失败原因：测试把一个仅用于设计说明的“ 五段执行证据链 ”文本当作必须渲染的页面标签。真实页面显示的是可点击的三个阶段证据标签。将测试断言改成检查实际且具有 ARIA 角色的“上下文来源”Tab，继续保留点击和英文导航验收。
## English
React compiled successfully, but a new Playwright assertion looked for explanatory prose that the UI does not render. Assert the actual accessible Context Provenance tab instead of nonexistent copy. The test still checks navigation and language switching.
## 验证 / Verification
- Failing run: Actions #44739283589, Playwright only.
- Full Windows CI rerun required after this fix.
## 下一步 / Next
Finish historical documentation indexing; publish only once E2E, .NET and Windows packaging pass.
