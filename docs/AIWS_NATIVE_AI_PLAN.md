# AI 原生系统路线：工作台主界面 + 本地小模型文件操作 + 模型路由

依据 Alpha 计划 M2/M4 细化。**这是路线，不是已完成功能。** 每阶段独立提交、独立验收。

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 1 | 基础文件工具：stat / mkdir / copy / move(重命名) / trash / restore；全部写操作走审批 DAG + Broker | **已实现（单元测试通过）** |
| 2 | 工作台文件管理器与全局指令栏、审批卡片、撤销入口 | **已实现（含真实浏览器端到端验证）** |
| 3 | 本地小模型：工具分级（只读自动 / 写需审批）、多步计划、本机系统/网络/下载信息只读工具 | **代码与测试已完成；数据集扩充与 LoRA、真实 2B 模型评测未做** |
| 4 | 模型路由：规则层 → 本地模型 → 官方 CLI（Claude Code / Codex，用户确认后升级），路由决策写入 DAG 审计 | **已实现（规则、升级限制、交接文件、审计；真实 CLI 联动未做）** |

## 已定的决策（用户确认）
- 删除只做“移到回收站”，不提供永久删除工具。
- 本地模型提议的只读操作免审批；写操作必须审批。
- 外部模型通过官方 CLI 接入，不使用 API 密钥。

## 网络、系统信息与下载：本地小模型只读、离线（用户澄清后的最终约束）
- 小模型**完全离线**：不联网、不下载、不调用云端。它只管理“下载信息”：读取进度、整理已下载的文件。
- 新增只读工具（模型可直接调用，自动执行）：`system.info`（内核/内存/负载/磁盘）、`network.status`（**只读取内核导出的本机状态**：网卡、本机 IP、默认路由、DNS 配置、套接字计数、吞吐；不创建套接字、不发包，测试强制）、`download.list`、`download.progress`（读取工作区 `downloads/` 内文件与 `.part/.crdownload/.aria2` 等状态；可选 `<名>.progress.json` 的 `totalBytes` 用于百分比和 ETA）。
- 模型**没有**任何下载/抓取工具；`browser.snapshot`、`runtime.test`、`project.scaffold`、`file.replace` 均不在模型允许集合中（测试固定）。模型服务单元已有 `IPAddressDeny=any` + `IPAddressAllow=localhost`，推理服务只监听 127.0.0.1。
- 下载由用户自己的浏览器或下载器完成；把下载目录指向工作区 `downloads/` 即可被读取。整理已完成下载用阶段 1 的文件工具（需批准）。

## 阶段 3 实现要点
- 单一来源：`aiws_toolplane.READ_TOOLS / FILE_WRITE_TOOLS`；任务、Broker、Agent、Workbench、本地模型均从此导入，不再各抄一份。
- 模型分级：读工具自动执行；`file.mkdir/copy/move/trash/restore` 可提议但永远生成待批准阶段；`file.replace` 不可提议（小模型不写文件内容）。
- 多步计划：`{"steps":[…≤8],"reason"}`，顺序依赖；单步提议保持兼容。
- **指纹由控制器计算**：模型提交 `expectedSha256` 会被拒绝；Agent 读取真实文件后补全。若某步触碰前面步骤已改动的路径（指纹会过期）或源文件不存在，整个计划被拒绝，要求拆小。
- 修复生产路径缺陷：此前 Workbench 把“已校验字典”交给 Agent 再校验，会因多余字段被拒；现改为传输 canonical 原始形态，Agent 独立重验并建阶段。
- 前端：计划预览标注每步“只读自动 / 需你批准”；写阶段显示将执行的参数；新增“批准并运行”。

## 阶段 1 实现要点
- 位置：`os/runtime/aiws_toolplane.py`；注册于 `aiws_tasks.WRITE_TOOLS`，因此未审批的写阶段不能 dispatch，Broker 再次核对。
- 路径规则复用 `_path()`：拒绝绝对路径、`..`、`.git`、`.ssh`、符号链接、跨挂载。
- 前置校验：copy/move/trash 需要 `expectedSha256`（目录为受界树指纹，>5000 项或含符号链接则拒绝）。
- 不覆盖：目标存在即失败；文件移动用 `link+unlink` 保证原子“不替换”。
- 回收站：`.aiws-trash/<id>/{payload,meta.json}`，上限 500 项，对 tree/search 隐藏，restore 会复核指纹。
- 暂不支持：目录复制、永久清空回收站。
- 模型暂不能提议写工具（`aiws_local_model.READ_TOOLS` 仅加入 `file.stat`），待阶段 3。

## 阶段 2 实现要点
- 后端：`workspace.tree` 新增 `dirs`（空文件夹可见）；新增只读工具 `file.trashList`；新增 `GET /api/v1/workspace/stat`、`/workspace/trash`。
- 前端：`GuestFiles.tsx` 改为目录树文件管理器；`src/model/fileOps.mjs` 为纯函数（指令解析、DAG 阶段构造、树构建，含 node 测试）。
- 指令栏（顶部，所有页面可用）：确定性语法 `mv/cp/rm/mkdir/restore` 及中文“移动/复制/重命名/删除/新建文件夹/恢复”。**不依赖模型**；自然语言留到阶段 3 由本地模型接管，同样只产出“待批准卡片”。
- 任何写操作先生成**批准卡片**（显示操作与 SHA-256 指纹），用户点“批准并执行”才 approve+dispatch；完成后提供“撤销（恢复）”，回收站面板可随时恢复。
- “放弃”仅在界面关闭卡片：任务阶段停留在 pending 且永不执行。后端尚无“取消任务”状态；如需在审计链中记录拒绝，需单独扩展任务状态机（后续项）。

## 阶段 4 实现要点（详见 [AIWS_MODEL_ROUTER.md](AIWS_MODEL_ROUTER.md)）
- `aiws_model_router.py`：L0 规则 → 本地模型 → 外部官方 CLI；**拒绝是最终结论，永不升级**；受限类别永不可外发；外部默认关闭；升级只是“提议”，由用户批准“交接文件”写入阶段。
- AIWS 不联网、不启动任何外部 CLI；交接文件只含指令与工作区文件名，不含内容或凭据，由用户自己拿去官方 CLI 使用。
- 路由决策（仅指令哈希）写入 DAG 审计 `route.decided`。
