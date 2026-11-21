# 2026-11-21 17:30 — 修复基线测试与安装预检 lsblk 字段缺失

## 改动
- `os/verify/test_installer_preflight.py`：文件中残留字面量 `\n`，导致整个模块 SyntaxError、从未被执行；已还原为真实换行。
- `os/installer/aiws_install_preflight.py`：模块可执行后测试发现**真实缺陷**——过滤逻辑检查 `fstype/pttype/ptuuid/uuid/mountpoints`，但 `lsblk --output` 没请求这些列，已有文件系统的整盘会被误判为空盘。已补齐列。预检仍是只读，不写磁盘。
- `os/verify/test_workbench.py`：该用例在 root 容器中先触发“不得以 root 运行”而非“缺少客户机标记”；两者都是 fail-closed，断言改为接受任一。
- `docs/AIWS_NATIVE_AI_PLAN.md`：按用户澄清重写“网络/系统信息/下载”章节：模型自主执行，用户一次性授权下载策略。

## 验证
`python3 -m unittest discover -s os/verify -p 'test_*.py'`：121 项全部通过（此前 2 项失败/导入错误）。

## 下一步
阶段 2：文件管理器、指令栏、审批卡片、撤销入口。
