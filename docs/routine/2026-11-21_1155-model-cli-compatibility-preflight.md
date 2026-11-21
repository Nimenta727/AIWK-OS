# 2026-11-21 11:55 — 修复 Qwen 2B 真实启动失败：llama.cpp 参数 ABI 检查

## 发现（来自真实 CI）
- AIWS real offline 2B inference baseline 运行 **44852710318** 编译 Debian 13 版本 llama.cpp、校验 GGUF SHA256、检查 non-root 容器权限均通过；运行 llama-server 时失败。
- 容器输出为 `error: invalid argument: --no-mmap`；因 server 在实际模型加载前就退出，不能据此判定模型性能或资源需求。失败的 CPU 推理后，QEMU 内部模型运行步骤未执行。

## 本次修改
- `os/model/ci/inference_smoke.py` 删除当前已固定 llama.cpp 版本不支持的 `--no-mmap`；统一 server_command() 参数构造，供真实 CLI 预检直接使用。
- 新增 `os/model/ci/check_llama_cli.py`，在运行真实 2B 推理之前调用**同一可执行程序**的 `--help`，检查本次 smoke 需要的 CLI flags，在小模型耗时加载前拒绝不兼容版本。
- `.github/workflows/aiws-real-model.yml` 添加预检步骤，并在 `docs/routine/README.md` 索引本记录。
- 只更改客户机测试容器和构建链，不增加 host 文件、kernel、GPU、hypervisor 或云端操作权限。

## 验证和已知限制
- 本次代码提交并不证明 CPU 推理或含 GGUF 的 QEMU 客户机加载成功；必须以本提交新触发的 `AIWS real offline 2B inference baseline` 工作流结果为准。
- `--help` 检查只能捕获公开选项不匹配，仍可能出现 GGUF 加载失败、上下文不足、模型输出不符合 JSON 等运行时问题。

## 下一步
1. 追踪 2B 真正 CPU 推理的模型加载、RSS、时延、JSON 工具建议正确率，并在失败时查看匿名诊断。
2. 运行完整的 model-inclusive Debian ISO + QEMU，要求在客户机内真正响应本地模型建议。
3. 扩充离线安全基准和端到端模型 → 审批 → DAG 任务验证，长期测试内存压力及用户可感知时延。
