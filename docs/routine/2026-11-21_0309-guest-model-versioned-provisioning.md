# 2026-11-21 03:09 — Offline local model version registry with hash-pinned import and rollback

## 变更
- 新增 os/runtime/aiws_model_registry.py：只允许在专用客户机内，将用户已审查许可且提供可信 SHA-256 的 GGUF 文件从客户机 workspace 导入私有 versions 目录，保存当前/上个版本和模型哈希清单。导入/回滚前检查模型服务已停止，禁止 host 目录、共享挂载、symlink、root、网络下载和任意命令。
- 通过不复制到多个挂载的硬链接 + 原子替换切换普通文件 aiws-local.gguf；版本元数据记录哈希，启动前再次 SHA 校验。服务一旦使用未经注册或篡改的权重则拒绝启动。标注许可只是来源声明，不能据此证明第三方量化的完整许可证。
- 新增 os/verify/test_model_registry.py，使用模拟 2 KiB GGUF 测试许可拒绝、错误哈希、版本导入、切换/回滚、篡改阻止及客户机环境拒绝。**测试文件不是实际可推理模型权重。**
- 本次只构建本地模型可验证的交付机制，真实 Qwen3.5-2B GGUF 尚未打包、运行、评测或微调；许可证与 gguf 转换模型质量需要后续验证。

## 文件
os/runtime/aiws_model_registry.py、os/verify/test_model_registry.py、本 routine。

## 下一步
模型启动脚本强制校验版本注册信息，后端 UI 根据注册状态阻止启动无来源权重；引入 guest-only 实际推理与资源/质量评测；评估误恢复、断电原子化/存储配额，进行版本回滚双检查。
