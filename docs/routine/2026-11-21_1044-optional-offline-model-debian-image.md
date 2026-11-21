# 2026-11-21 10:44 — Opt-in offline-model-inclusive Debian guest ISO

## 本次代码
- os/debian/build.sh 新增可选打包开关 AIWS_OS_BUNDLED_MODEL_GGUF、AIWS_OS_BUNDLED_LLAMA_SERVER、两个预先认可的 SHA256 值和 AIWS_OS_MODEL_LICENSE_REVIEWED=1。在隔离构建环境先验证文件存在、不是符号链接、完整哈希和 GGUF magic，再将模型及 llama-server 放入只读镜像。未提供这些变量的常规 ISO 完全不捆绑模型。
- aiws-open-workbench 在拥有 model-preload root-owned manifest 时，仅首次调用此前已实现的 `--import-bundled` 守卫，复制到客户机用户私有模型版本库；若失败则继续启动确定性的文件/任务系统，不会自动联网、不会自动开启小模型。
- 需要事先通过模型来源、量化许可证、二进制文件来源与完整 SHA256 审核。没有用户主机共享目录、宿主 GPU 或 Hypervisor API。
- 文件：os/debian/build.sh、os/debian/config/includes.chroot/usr/local/bin/aiws-open-workbench、本 routine。
## 下一步
CI 真实 Qwen3.5-2B llama.cpp CPU 基线完成后，在单独的带模型 ISO 中用 QEMU 进行实际推理与内存测量；完成 guest image model benchmark 后才能声称完整模型在 OS 中运行。继续核对 UEFI A/B 引导和 QEMU GUI 测试。
