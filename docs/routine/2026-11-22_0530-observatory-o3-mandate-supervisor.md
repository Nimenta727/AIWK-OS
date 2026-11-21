# 2026-11-22 05:30 — O3：授权令牌与监督器

## 改动
- 新增 `aiws_mandate.py`、`aiws_supervisor.py`（均已加入 `build.sh`）；`aiws_cli_adapters.py` 增加 `turns` 计数；`aiws_observatory.py` 增加预算视图与运行审批，并排除 supervisor/router 的“用量未知”统计；工作台新增 builder 接口。
- 前端 `Observatory.tsx`：预算条、构建通道状态、收件箱运行审批、“构建”卡片（授权并开始 / 停止 / 撤销）。
- 测试：`test_supervisor.py`（29）、`test_builder_api.py`（7）、`fixtures/fake_cli.py`（合成假 CLI）；`test_observatory.py` 更新并新增 1 项。

## 发现并修复
- 监督器自查：审批超时与拒绝的原因判断写反、输出流关闭但进程仍存活时会卡住、审批等待时间不应计入时间上限、每个事件都读一次数据库。
- 假 CLI 自相矛盾（逐条用量与最终总量不一致）。
- 观察台把 supervisor 会话计入“用量来源未知”，使审计灯无谓变黄。

## 验证
- Python 全量 256 项通过（监督器测试连跑 3 次稳定）；前端 `tsc`、`npm test`（52）、`vite build` 通过。
- 真实浏览器（假 CLI 启动器）：流程见观察台方案第 14 节。

## 限制
默认关闭；O4 前隔离较弱；检测是尽力而为；CLI 参数名/输出格式未验证（O6）。

## 下一步
O4：构建通道的内核级隔离（独立 UID、仅项目目录可写、域名白名单代理 + nftables），需在 QEMU 客体里实测。
