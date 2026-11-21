# 2026-11-21 11:44 — Make local model service lifecycle an approved persistent guest DAG

## 修复架构旁路
- 过去模型启停由 Workbench Controller 直接执行 systemctl --user，虽然只在 guest，但未经过统一持久任务和审计，留下单独执行路径。
- os/runtime/aiws_guest_ops.py 新增固定且仅限 aiws-local-model.service 的 service.enable/service.disable，均是 WRITE_TOOLS，只有经 GuestTaskStore 显式审批后可调度；enable 前验证 model registry 或 root-owned bundled GGUF 完整 SHA，固定 systemctl --user enable/disable --now，更新客户机用户私有状态标志，不提供任意 shell 或 root。
- Controller.configure_model 现只创建**未执行的**单阶段服务任务。React 本地助手页的按钮改成提交审批任务，展示任务详情，用户必须另点批准+执行；不再调用 systemctl。 LocalPlanner 运行时重新读取客体持久状态标志以正确刷新模型服务状态。
- test_guest_ops.py 增加启停未经审核拒绝、错误服务拒绝、禁用通过固定 runner 的测试。所有测试仍仅操作临时 guest fixture，不操作宿主真实 systemd。
- 文件 aiws_guest_ops.py、aiws_workbench.py、aiws_local_model.py、GuestTaskStudio.tsx、test_guest_ops.py、本 routine。
## 验证和下一步
需 CI 测试、React 构建、QEMU 实际用户服务验收。模型真实推理 workflow 当前仍需修正 llama-server 启动失败；bootloader A/B 回退仍待完整固件实证。模型永远不拥有 systemd 直接执行权限。
