# 2026-11-22 11:00 — O5：小模型框架省资源与省 token

## 改动
- 新增 `aiws_model_gate.py`（按需启动/空闲卸载网关）、`aiws_model_schema.py`（约束输出 schema + 测试用迷你校验器）；`aiws_local_model.py`：自适应 `max_tokens`、截断才重试、稳定前缀 + `cache_prompt`、结果缓存、schema 模式及 400 回退、`model.json` 配置、`status()` 带网关信息；工作台把缓存命中记为零成本。
- 启动脚本两处（`os/model/aiws-local-model.sh` 与镜像内 `usr/local/bin/aiws-local-model`）改为经网关启动 llama-server（内部端口 18081）；客体冒烟脚本改为从 `/gate/status` 取真实冷启动时间与 llama-server PID；`build.sh` 打包网关与 schema；观察台显示模型已加载/已卸载及 RSS。
- 测试：`test_model_gate.py`（16）、`test_model_schema.py`（6）、`test_model_efficiency.py`（19，含规划器↔真实网关联调）、`test_model_wiring.py`（7）；`fixtures/fake_llama.py`（合成的假 llama-server）。

## 发现并修复
1. 网关自查：冷启动等待时一直持有状态锁，会让 `/health` 与状态查询卡住；拆成独立的启动锁。
2. 结果缓存键里包含“最近任务列表”，而每次规划都会新建任务，导致缓存在真实流程里永远命不中；改为只用“指令 + 文件清单”。
3. 约束 schema 最初会放行 `.git/…` 之类路径而验证器拒绝；补上受保护目录的否定断言，并用变异测试固定“schema ⊆ 验证器”。
4. **既有不一致**：仓库里的 `os/model/aiws-local-model.sh` 与镜像里的 `aiws-local-model` 并不相同（后者多了模型预置与校验），本次两处都改了，但没有合并两份——后续应统一。

## 验证
- Python 全量 348 项通过；前端 `tsc`、`npm test`、`vite build` 通过。网关本身开销约 1 ms（假 llama，本机）。
- **未验证**：任何真实模型指标；`cache_prompt`/`json_schema` 的服务端行为；客体冒烟脚本改动。

## 下一步
O6：用你的环境录制真实 CLI 输出并核对字段与计费；在真实客体上跑 v1/v2 评测集与 `aiws-builder-selftest`，并测量冷启动、卸载前后 RSS。
