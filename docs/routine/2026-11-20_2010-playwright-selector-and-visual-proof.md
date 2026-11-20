# 2026-11-20 20:10 — Windows UI 浏览器冒烟测试定位修复与视觉证据归档

## 结果与原因
V1.8.1 第一轮 GitHub Windows Native CI 的 TypeScript/Vite 正式编译和 33 项 Node 测试均通过。新增的 3 项 Playwright Edge 浏览器互动测试中，导航与窄视图检查器 2 项通过；创建任务测试因测试脚本的宽泛选择器同时匹配侧栏与顶部两个真正存在的“新建任务”按钮而报 strict mode failure，并非用户界面点击无响应。

## 本次修改
- `desktop/AIWorkstation.Frontend/tests/e2e/workbench.spec.mjs`：使用具体顶部按钮选择器 `.top-create` 测试创建流程；增加协作总控台及计划中心桌面截图，供真实渲染审阅。
- `.github/workflows/native-desktop.yml`：无论 UI 测试成功与否，上传 `test-results/` 下的页面截图及 Playwright trace，以便复现并诊断交互问题。
- 新增此 routine；原功能代码保持不变。

## 验证 / Validation
- 首轮 CI：浏览器 2/3 通过、Vite 与 33 项 Node 测试成功；Windows .NET 编译尚因前置 UI 测试失败而未启动。
- 修复后将重新跑 Node/Playwright + .NET/WPF/EXE 全部流水线，不以未通过的检查宣称成功。

## 下一步 / Next steps
1. 核对新 Windows Edge 浏览器测试 3/3 成功，确认新编译的 UI 截图与布局。
2. 完成原生 WPF/.NET 构建、核心回归测试、EXE+ui-dist 交付包验证。
3. 在用户 Hyper-V 虚拟机上进行 WebView2 弹窗、目录选择、真实终端与 DPI/IME 点击实测；对尚存问题继续补丁与 routine 日志。
