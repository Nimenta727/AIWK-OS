# 2026-11-21 21:30 — P3–P6：时间线、变更审查、能力索引、宿主模型通道

## 改动
- **观察台**：新增共享时间轴（按模型/工具/构建/系统/错误分道，错误标红，无事件的静默段标灰）和会话的 token 累计曲线（含预算线）。没有动画、没有装饰；未上报用量不画成 0。
- **变更审查**：`aiws_changes.py`（只读 `git status/diff`，加固参数，路径受工具平面同款限制）、`GET /api/v1/changes[/diff]`、资源管理器里的「变更审查」页（文件 +/− 数、点击看 diff）。
- **能力索引**：`aiws_capabilities.py`（工具 + skill + 记忆统一检索，确定性 BM25，含中文）、`GET /api/v1/capabilities?q=`、`GET/POST /api/v1/memory`；`os/skills/` 首批 5 个 skill + `build_manifest.py`；镜像构建会安装并固定哈希（改过的 skill 不加载）。
- **宿主模型通道**：`aiws_model_channel.py`（客体回环 HTTP ↔ virtio-serial ↔ 宿主回环 llama-server），单并发、白名单、上限、日志不含内容。
- 文档：`docs/AIWS_NATIVE_SHELL_PLAN.md`（方案、插件功能对照、未完成清单）。

## 文件
`workbench/src/model/timeline.mjs`、`workbench/src/os/{Timeline,ChangesView}.tsx`、`workbench/src/os/{Observatory,OsWorkbench}.tsx`、`workbench/src/os/shell.css`、`workbench/tests/timeline.test.mjs`；`os/runtime/{aiws_changes,aiws_capabilities,aiws_model_channel}.py`、`aiws_workbench.py`、`MODULES`；`os/skills/*`；`os/debian/build.sh`；`os/verify/{test_changes,test_capabilities,test_model_channel}.py`；`docs/AIWS_NATIVE_SHELL_PLAN.md`

## 验证
- Python 全量 466 项通过（2 项跳过为既有）；前端 `tsc`、`npm test` 40 项、`vite build` 通过。
- 刻意测过的风险：仓库里配置的 `diff.external`/`core.fsmonitor` 不会被执行；符号链接/`..`/`.git` 路径被拒；skill 哈希不符/过大/符号链接被跳过；记忆拒绝疑似密钥；通道的非白名单路径在客体与宿主两侧都被拒；响应 id 不一致会被识别。
- **未验证**：真实浏览器渲染（时间线/diff 的视觉效果）；真实 QEMU virtio-serial 与 Windows 命名管道联调；检索在真实用户语句上的效果。

## 已知问题
- 规划器尚未使用能力索引（需重跑模型评测）；客体侧通道单元未加入镜像；双盘未做。
- 本轮结束时 `git push` 被权限审核拦下，提交只在本地分支（见下一步）。

## 下一步
见 `docs/AIWS_NATIVE_SHELL_PLAN.md` 第 6 节：先启动真实镜像核对外壳/输入法 → 任务产物关联 → 规划器接入检索并重跑评测 → 通道联调 → 双盘评审。
