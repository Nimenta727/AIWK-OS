# AIWS OS small model / 本地小模型系统集成

**状态：本地建议层与客户机启动配置已实现，真实权重/推理和微调尚未验收。**

目标是让一个本地 9B 模型（Qwen3.5-9B）成为 AIWS 工作台内部的路由器、日志阅读员和任务建议器（其“专用 agent 接口”见 [AIWS_LOCAL_AGENT.md](AIWS_LOCAL_AGENT.md)），减少云端 Token，并不替代确定性的文件系统接口、DAG 调度、权限审核及审计。

**产品模型固定为 Qwen3.5-9B（Q4_K_M GGUF，约 5.7 GB，sha256 `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8`，来源 unsloth/Qwen3.5-9B-GGUF）。** 2026-11-22 已核对：模型卡、GGUF 元数据与 LICENSE 全文均为 Apache-2.0；第三方量化的附带条件仍需发行前人工确认。此前评测的 2B 已撤出产品（登记表只认 9B；CI 流水线冒烟用的小模型只在 CI 专用标记存在时才放行）。

**放在哪里跑（重要）**：这个模型用客户机 CPU 跑很慢——实测（4 核、Q4_K_M）回答一个路由问题约 9 s，读一份压缩后的日志约 90 s；**常驻内存实测 10.2–10.7 GB**（`llama-server` 本体，commit a956a85，4 核、Q4_K_M、上下文 8192、单槽：堆约 5.5–5.8 GB + 权重映射约 4.7 GB；启动守卫按“权重 + 5 GiB”判断），默认 6 GiB 虚拟机放不下，启动脚本会明确拒绝（退出码 75）。宿主显卡经 virtio 通道（`aiws_model_channel.py`）的代码和测试都在，会比 CPU 快得多，但**当前镜像和 QEMU 启动脚本里还没有接线**，所以**现在可用的只有客户机 CPU 这条路**（慢，需要约 11 GiB 内存）。**发布的 ISO 不带权重**：客户自己下载并导入，步骤见 [AIWS_MODEL_WEIGHTS.md](AIWS_MODEL_WEIGHTS.md)。该模型 32 层里只有 1/4 保留 KV 缓存（其余为状态空间层），8192 上下文的缓存约 256 MiB。

**混合架构提醒**：状态空间层的前缀缓存复用与纯 Transformer 不同，不要假设“稳定前缀=一定命中缓存”，以服务端 `timings.cache_n` 实测为准（客户端会记录）。

## 组件边界
- os/runtime/aiws_local_model.py：严格只允许 127.0.0.1:18080 的非代理推理连接，默认 disabled，JSON 工具建议必须经过 read-only allowlist、参数 schema 和相对 guest 路径验证。
- /usr/local/bin/aiws-local-model：拒绝 root/无 guest 标记/非 VM；仅接受客体用户模型目录中的 aiws-local.gguf；启用 CPU 模式 --gpu-layers 0，**没有任何宿主 GPU passthrough**。
- /etc/systemd/user/aiws-local-model.service：可选启动单元，不在默认系统启动；模型缺失时工作台和文件/DAG 仍正常运行。接入方式为客体用户在授权环境安装 llama.cpp，再导入经许可和哈希验证的模型到客体个人模型目录，显式开启服务及工作台的 AIWS_LOCAL_MODEL_ENABLED=1。
- 工作台可以向模型提问并显示建议，但模型不能执行工具；需要独立创建/审核 DAG。无模型时绝不自动调用云端。
- 所有模型操作仅在客户机内部，不授权 host shell、主机文件、内核、设备、虚拟机管理接口或共享挂载。

## Token 预算层级
1. 文件查看、检索、状态、工具执行与任务生命周期均由确定性代码完成，云端 Token = 0。
2. 本地 9B 路由（local/flash/pro 判档）、日志关键行筛选、工具参数建议在本机完成，云端 Token = 0。
3. 复杂多文件变更、深入重构才在用户批准后按需调用远程模型；默认离线运行，离线场景依旧使用工具和本地模型。

## 微调与质量门槛
先建立专用的中英双语意图样本、独立评测拆分和 schema/安全检查，再在独立 guest 中试验 LoRA/QLoRA。数据必须属于合成或明确授权样本，严禁自动收集用户私有项目内容、凭据或主机目录作为训练材料。记录原模型 SHA、adapter SHA、评测集版本、准确率、拒绝越权成功率、性能和回滚方案。

此阶段没有实际模型权重，也没有训练后的 LoRA。之后才进行性能对比；若微调并未稳定优于基线，不作为默认内置版本。

参考：
https://huggingface.co/Qwen/Qwen3.5-9B
https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
https://huggingface.co/docs/trl/peft_integration


## 模型开关与资源限制
工作台提供显式启用/关闭按钮，只在客户机预装模型文件后允许启用；调用严格固定的 guest systemd user service，不执行模型产生的任意命令。单元使用 MemoryMax=12G、CPUQuota=400%、仅允许 guest loopback 网络地址；这是客户机进程资源限制，不是 GPU 显存的实验保证。若资源不足，服务会失败，工作台和确定性任务管理不应随之失效。

P0 GUI 已在 GitHub run 44787989404 完成真实 Chromium 可见窗口与 Selenium 文件/DAG 点击验收；本地小模型仍未装载，测试确认其为可选状态。


## 2026-11-21：独立评测与安全拒绝协议 / Held-out benchmark

- 具体协作微调标准、数据分区、模型登记、评测门槛与回滚条件：**[AIWS_MODEL_FINETUNING_STANDARD.md](AIWS_MODEL_FINETUNING_STANDARD.md)**。
- 固定的 26 条中英文合成 held-out smoke 案例：os/model/ci/heldout_v1.jsonl。CI 真实 QEMU 客户机调用同一 LocalPlanner、校验输出，仅通过串口传出工具准确率、精确参数准确率、越权显式拒绝率、schema 有效率、p50/p95/max、峰值 VmHWM 和加载时延。独立发行门禁需扩展到 ≥200 条新案例。
- 新的明确拒绝建议 tool=refuse、arguments={} 为**终止状态**，不能直接生成可调度阶段。不能用只读工具回避越权测试，也不能将 JSON/schema 拦截计作模型主动拒绝。
- 截至该代码变更，真实模型 QEMU 评测结果 **NOT VERIFIED**；不能把代码可运行或模拟服务测试当成真机达标。2026-11-22 起产品模型为 9B：路由与读日志的离线评测见 `docs/routine/2026-11-22_1032-…`；规划器的 held-out 门槛尚未在 9B 上重跑。
