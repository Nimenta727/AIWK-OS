# 2026-11-22 01:00 — O1：事件模式、CLI 适配器、事件存储

## 改动
- 新增 `aiws_events.py`（事件模式、脱敏、`EventStore`）与 `aiws_cli_adapters.py`（Claude/Codex 适配器、回放）；均已加入 `os/debian/build.sh` 打包清单。
- 新增 `os/verify/fixtures/cli/`（7 份**手写合成**样本 + README）与 `test_events.py`（25 项）。
- 更新 `docs/AIWS_OBSERVATORY_PLAN.md`（O1 状态与实现记录）。

## 发现并修复
1. 脱敏缺陷：`Authorization: Bearer <令牌>` 只替换了单词 Bearer，令牌漏出。已修并有测试。
2. 汇总缺陷：从未上报的字段（如 `cacheWrite`）被显示为 0；改为 `null`（未知）。

## 验证
- Python 全量单元测试 205 项通过。模块无网络/进程能力（静态检查）。
- **未验证**：真实 Claude Code / Codex 输出（样本是手写近似）；`turn` 范围 token 的累计/增量语义。

## 下一步
O2：观察台首页（预算条、token 面板、任务板、调用状态条、审计结论、“需要你”收件箱）与“高级”抽屉；需要先给 Workbench 加只读事件接口。
