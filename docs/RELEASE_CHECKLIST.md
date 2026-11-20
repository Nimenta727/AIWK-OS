# V1.9 Preview release checklist / 发行验收清单

## Automated / 自动测试
- [ ] Node projection tests (including missing token data and unsafe path filtering) / 前端逻辑测试
- [ ] Playwright Edge UI interactions (navigation, observability, language switching) / 浏览器点击验证
- [ ] .NET WPF build and core smoke tests / 原生编译与核心测试
- [ ] Python legacy regression / 旧版 Python 回归
- [ ] Windows x64 self-contained ZIP includes `WindowsAIWorkstation.exe` and `ui-dist/index.html`
- [ ] ZIP SHA-256 generated and published alongside release notes
- [ ] GitHub Release tagged as prerelease; source commit and Actions run linked
- [ ] Historical docs and original test evidence preserved / 历史证据保留

## Manual Hyper-V acceptance / 人工虚拟机验收（不可用 CI 代替）
- [ ] Non-admin VM, backup, workspace guard, executable unprivileged / 非管理员用户与独立备份
- [ ] WebView2 cold startup, window resizing, DPI and bilingual navigation / 启动及界面
- [ ] Multiple tasks, DAG navigation, stage inspector, approval gates / 多任务与审批
- [ ] Native folder picker, GUI dialogs, Chinese IME and keyboard-only operation / 文件选择与输入法
- [ ] ConPTY interactive terminal, Unicode output, resize and process lifecycle / 终端
- [ ] Real Git repository: added/deleted/renamed files, snapshots, commit and diff / 真实仓库
- [ ] No automatic model call from read-only dashboards / 可视化本地读取不产生模型调用
- [ ] Backup, task migration and interrupted process reconciliation / 恢复

**Publishing rule / 发布规则**：Only the automated checks can be marked green by GitHub Actions. Until manual acceptance is independently recorded, the release remains **Preview**, never “stable / production-ready”.
