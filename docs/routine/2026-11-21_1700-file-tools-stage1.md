# 2026-11-21 17:00 — 阶段 1：基础文件工具（stat/mkdir/copy/move/trash/restore）

## 做了什么
- `aiws_toolplane.py` 新增 6 个工具：`file.stat`（只读）、`file.mkdir`、`file.copy`、`file.move`（含重命名）、`file.trash`、`file.restore`（均为写）。
- 注册到 `aiws_tasks`（`WRITE_TOOLS`）→ 自动进入审批 DAG；`file.stat` 加入 Broker 直读、Agent 直读、Workbench 只读、本地模型只读清单。
- 新增 `os/verify/test_fileops.py`（12 项）：路径逃逸、符号链接、不覆盖、哈希冲突、回收站往返/篡改/冲突、写工具不在 MCP/模型/直读清单、未审批不能 dispatch。
- 新增 `docs/AIWS_NATIVE_AI_PLAN.md`，更新 `AIWS_AGENT_TOOL_FABRIC.md`。

## 安全设计
无永久删除工具；不覆盖；哈希/目录指纹前置校验；回收站受界、对搜索隐藏、复原复核指纹；仍是应用层 fail-closed，同 UID 限制不变。

## 验证
`python3 -m unittest discover -s os/verify -p 'test_*.py'`：116 项，新增 12 项通过。
**2 项原有失败，与本次无关**：`test_installer_preflight`（模块第 27 行语法错误导入失败）、`test_workbench.test_guest_service_in_dag_denied_without_vm_marker`（在 root 容器里先触发“不得 root”错误，断言文案不同）。真实 QEMU/GUI 未运行。

## 下一步
1. 修复上述 2 项原有失败（安装预检语法、该测试的环境假设）。
2. 阶段 2：GuestFiles 文件管理器 + 指令栏 + 审批卡片。
3. 阶段 3：模型工具分级、多步计划、数据集；网络/下载工具按 `AIWS_NATIVE_AI_PLAN.md` 约束设计。
4. 阶段 4：模型路由（官方 CLI，用户确认升级）。
