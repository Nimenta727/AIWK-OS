# 模型路由 / Model router

**状态：工程实现，已有单元与浏览器端到端验证；未与真实 Claude Code / Codex CLI 联动。**

## 目标与边界
决定一个请求“在哪里处理”，而不是处理它。路由器不联网、不启动进程、不调用任何模型（测试固定：模块只导入 `hashlib/json/re/shutil`）。

| 层 | 作用 |
| --- | --- |
| L0 规则 | 受限类别 → 只交本地模型；文件/系统/下载信息类 → 本地；代码编写/设计/分析类 → 外部候选（`claude`/`codex`/`dual`）；无法判断 → 先本地 |
| L1 本地结果 | `ok` 使用结果；`refused` **最终**；`invalid`/`unavailable` 才可能提议升级 |
| L2 外部官方 CLI | 只生成**交接文件**（`handoff/<id>.md`），由用户确认并自行使用 |

## 不变量（均有测试）
1. 拒绝是最终结论：不会为了绕过限制转交更强的模型（也没有“交接”后门：受限请求的 `/route/handoff` 返回 403）。
2. 受限类别（联网/下载控制/shell·root/宿主机/永久删除/写入内容/绕过审批审计/路径逃逸/云端或外传）永不可外发。
3. 外部默认关闭；`~/.config/aiws/routes.json` 严格校验（未知键、类型、长度、符号链接、>4KiB 一律拒绝并回到默认）。
4. 升级只是提议；交接文件的写入是需批准的 DAG 阶段（先 `file.mkdir handoff`，再 `file.replace`）。
5. 交接文件只含指令与文件名（≤24 个，过滤控制字符），不含文件内容、凭据、宿主信息。
6. 审计 `route.decided` 只存指令的 SHA-256、路由、规则、受限类别，不存指令文本。

## 配置（`~/.config/aiws/routes.json`）
```json
{"externalEnabled": false, "providers": {"claude": true, "codex": true},
 "extraLocalKeywords": [], "extraExternalKeywords": []}
```
界面只读展示；**目前不能在界面里编辑**（避免让网页写客户机配置文件），请直接编辑该文件。

## 接口
`POST /api/v1/route`（仅规则，无副作用）· `POST /api/v1/route/handoff`（需 CSRF；受限/未启用 → 403）· `GET /api/v1/route/config` · `POST /api/v1/model/plan` 现在会先路由，可能返回 `routed: external|manual|local-failed` 或带 `followUp` 的拒绝。Agent IPC 新增 `task.route`。

## 规则质量（如实）
规则是手写正则/关键词。评测集 `heldout_v2.jsonl` 对路由器**只有一次未污染的结果**：正常请求 135/142 留在本地（95.1%），越权请求 96/100 不可外发（96%）；失败暴露两个通用缺陷（文件名 `design.pdf` 被当成设计任务；“测试能不能连上 IP/域名”“联网搜索”未识别），修复后同一数据集已被路由器“用过”，现在只能当回归测试（142/142、100/100 不能当作泛化指标）。另有手写的独立短句测试。**真实用户措辞的泛化尚未验证。** 即使规则漏判，仍有第二道防线：本地模型的拒绝是最终结论，外部升级还要用户确认。
