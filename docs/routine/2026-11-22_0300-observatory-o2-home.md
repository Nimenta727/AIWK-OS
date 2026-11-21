# 2026-11-22 03:00 — O2：观察台首页与“高级”抽屉

## 改动
- 后端：`aiws_observatory.py`、`GuestTaskStore.overview()`、Agent IPC `task.overview`、`/api/v1/observatory` 与 `/observatory/events`；工作台在模型规划时写入路由/本地模型事件；本地模型 token 取自 llama-server 的 `usage`；`LocalPlanner.take_usage()`（线程局部）。
- 前端：`Observatory.tsx`、`model/observatory.mjs`（纯函数 + 7 项测试）；`OsWorkbench.tsx` 默认首页改为观察台，原页面收进“高级工具”；输入框先走确定性文件命令语法（不调模型）。
- 打包：`aiws_observatory.py` 加入 `build.sh`；打包回归测试现在同时识别 `import x` 与 `from x import`（此前漏检了本次新增的 `import aiws_observatory`）。
- 文档：观察台方案 O2 状态与实现记录。

## 验证
- Python 全量测试通过（新增 `test_observatory.py` 14 项）；前端 `tsc`、`npm test`（52 项）、`vite build` 通过。
- 真实浏览器（回环 mock 模型）：默认首页是观察台；示例数据有明确标注；事件详情点开才加载且不含样本正文；高级工具默认折叠；自然语言→任务→收件箱批准→文件移动生效，批准前磁盘无变化；本地模型 token 显示为模型自己上报的 412+96；精确命令直接进入文件管理器；无页面错误。
- **未验证**：真实多智能体场景下任务板的可读性；真实 CLI 数据；QEMU 内 GUI。

## 已知限制
任务板目前是紧凑列表 + 状态条，不是图；预算条等 O3；构建通道状态等 O4。

## 下一步
O3：授权令牌（Mandate）与监督器（超预算/越界终止，用假 CLI 验证），随后预算条接入观察台。
