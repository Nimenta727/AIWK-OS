# 2026-11-21 09:14 — 修复 QEMU 内核候选测试的诊断盲区

## 变更
- 最新真实 QEMU 失败日志 44795328720 显示 GUI 文件查看与普通 DAG 调度通过，但 kernel.stage 的完成等待超时（Selenium TimeoutException）。
- 修改客户机 `aiws_gui_smoke.py`：不更改成功标准，仍须真实 GUI 中显示 COMPLETED、deployed:false，并从客户机 HTTP 任务存储核实阶段结果。
- 出现异常时额外输出 guest API 当前任务、阶段 state、error、result 和 GUI 文本，便于区分后端执行器失败与前端状态轮询失败；仅在一次性测试虚拟机中输出这些诊断。
- 修改文件：`os/debian/config/includes.chroot/usr/local/lib/aiws/aiws_gui_smoke.py` 和本例行记录。

## 验证 / 下一步
需要新的 Debian ISO/QEMU CI 输出明确根因；根因修复后重新跑真实窗口点击和 DAG。不得通过删除或弱化内核候选测试求绿。内核部署/回退、真实模型推理仍未完成。
