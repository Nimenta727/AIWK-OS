# 2026-11-21 00:57 — Host isolation hardening and P0/P1 gate register

## 变更及原因
- 用户强调的四项主线写入强制验收登记：P0 GUI 可视+点击，P0 Windows 任务/计划/DAG/Agent/审计迁入 Linux，P1 NixOS 真正构建/启动，P1 客户机权限/隔离/恢复，不允许被模型、文件和内核新功能取代。
- 用户指定的宿主机零控制是不可让步原则：任何 AI 内核管理仅限独立 guest kernel 源码/版本化镜像/回滚，拒绝所有 host 文件、root、hypervisor 控制、设备直通与共享挂载接口。
- 修复潜在路径递归漏洞：此前仅阻止目标路径位于嵌套 mount，工作区树遍历仍可遍历被动挂载的目录。现在工作区检测一旦发现任何嵌套 mount 就 fail closed，降低目录遍历越界风险。

## 修改文件
os/runtime/aiws_guest_boundary.py，os/verify/test_guest_boundary.py，docs/AIWS_OS_PRIORITY_GATES.md，本 routine。

## 测试与限制
更新测试覆盖嵌套 mount 存在时工作区根本身被禁止；须经本次静态 CI 实测。No host security guarantee: guest root 可尝试改变隔离策略；host VM manager 与硬件隔离必须有独立安全配置。当前四项验收尚未全部完成。

## 下一步
按 docs/AIWS_OS_PRIORITY_GATES.md 顺序：真实 GUI 交互 → guest 持久任务/DAG → NixOS 构建/开机 → guest broker、资源和恢复；AI 文件组织/离线模型/内核编辑只作为这些里程碑的受控子模块。
