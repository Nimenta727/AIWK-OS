# 2026-11-21 · 旧代码移入 Git 历史、文档归档、前端精简

## 做了什么
- **旧代码从主工作树移除（保留在 Git 历史，最后包含它们的提交 `f6d5090`）**：Windows 原生工作台（`desktop/AIWorkstation.{Core,Core.SmokeTests,Desktop}`）、旧 Python 控制平面（`aiws/`、`app.py`、`web/`、`tests/`）、Windows 脚本（`scripts/`）、NixOS 配方（`flake.nix`、`os/platforms`）、借用的 T3 Code 原语（`third_party/`）。取回：`git show f6d5090:<路径>`。
- **前端精简并改名**：`desktop/AIWorkstation.Frontend` → `workbench/`；删除 Windows 版 App、18 个旧组件、8 个旧纯逻辑模块及其测试、Playwright e2e 与配置、xterm 依赖；`main.tsx` 只渲染 OsWorkbench；工作台服务不再注入 `os-bridge.js`。包名 `@aiws/workbench`，版本 `0.2.0-preview.1`。打包体积从 >500 kB 降到 338 kB（gzip 105 kB）。
- **CI**：删除 `native-desktop.yml`、`publish-preview.yml`、`tests.yml`（旧 Python/Windows）；镜像构建工作流去掉 NixOS 任务并更新路径。
- **文档**：旧文档 25 份 + `archive/` + 旧 `HISTORY.md` 移入 `docs/history/`（`routine/` 未动）；新写 `docs/README.md`（当前索引）、`docs/SECURITY.md`（面向当前 OS）、`docs/CODEBASE_MAP.md`（当前结构）；`docs/history/README.md` 记录被移出的内容与取回方法。
- **版权文件**：`NOTICE` 中 T3 Code 改为“历史说明”（代码与其 MIT 声明在 Git 历史里）；`THIRD_PARTY.md` 去掉 t3code 行；`test_legal.py` 改为断言工作树中没有收录第三方源码。

## 验证
- Python 438 项通过；前端 `tsc`、30 项 node 测试、`vite build` 通过；当前文档的相对链接检查除 README（待重写）外无断链。

## 已知问题 / 下一步
- 根 README 仍是上一版，下一步随发行信息重写。
- `aiws_windows_compat.py`（旧 Windows 任务历史导入）、`aiws_crossplatform.py` / `aiws_codeintel.py`（C#/Swift 代码智能与模板）仍保留在运行时：它们是被测试覆盖的工具，涉及运行时、UI、镜像 GUI 冒烟脚本和模型工具目录，一并删除风险较大，列为后续精简候选。
