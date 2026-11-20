# AIWS OS small model / 本地小模型系统集成

**状态：本地建议层与客户机启动配置已实现，真实权重/推理和微调尚未验收。**

目标是让 1–3B 小模型成为 AIWS 工作台内部的意图解析器和任务建议器，减少云端 Token，并不替代确定性的文件系统接口、DAG 调度、权限审核及审计。

建议初期试用 Qwen3.5-2B 的 instruction/post-trained 官方权重，经专用授权的 GGUF 量化转换后运行在 llama.cpp。官方权重 Apache-2.0；发行版与第三方量化的授权仍需检查。3–5GB 显存只是目标约束，必须量化测量上下文 KV 缓存、CPU 使用率与延迟；不承诺静态显存。

## 组件边界
- os/runtime/aiws_local_model.py：严格只允许 127.0.0.1:18080 的非代理推理连接，默认 disabled，JSON 工具建议必须经过 read-only allowlist、参数 schema 和相对 guest 路径验证。
- /usr/local/bin/aiws-local-model：拒绝 root/无 guest 标记/非 VM；仅接受客体用户模型目录中的 aiws-local.gguf；启用 CPU 模式 --gpu-layers 0，**没有任何宿主 GPU passthrough**。
- /etc/systemd/user/aiws-local-model.service：可选启动单元，不在默认系统启动；模型缺失时工作台和文件/DAG 仍正常运行。接入方式为客体用户在授权环境安装 llama.cpp，再导入经许可和哈希验证的模型到客体个人模型目录，显式开启服务及工作台的 AIWS_LOCAL_MODEL_ENABLED=1。
- 工作台可以向模型提问并显示建议，但模型不能执行工具；需要独立创建/审核 DAG。无模型时绝不自动调用云端。
- 所有模型操作仅在客户机内部，不授权 host shell、主机文件、内核、设备、虚拟机管理接口或共享挂载。

## Token 预算层级
1. 文件查看、检索、状态、工具执行与任务生命周期均由确定性代码完成，云端 Token = 0。
2. 本地 2B 意图分类、文件相关性筛选、工具参数建议在 guest 完成，云端 Token = 0。
3. 复杂多文件变更、深入重构才在用户批准后按需调用远程模型；默认离线运行，离线场景依旧使用工具和本地模型。

## 微调与质量门槛
先建立专用的中英双语意图样本、独立评测拆分和 schema/安全检查，再在独立 guest 中试验 LoRA/QLoRA。数据必须属于合成或明确授权样本，严禁自动收集用户私有项目内容、凭据或主机目录作为训练材料。记录原模型 SHA、adapter SHA、评测集版本、准确率、拒绝越权成功率、性能和回滚方案。

此阶段没有实际模型权重，也没有训练后的 LoRA。之后才进行性能对比；若微调并未稳定优于基线，不作为默认内置版本。

参考：
https://huggingface.co/Qwen/Qwen3.5-2B
https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
https://huggingface.co/docs/trl/peft_integration
