# 2026-11-21 02:00 — Optional guest-only llama.cpp service interface

## 变更
新增 AIWS OS 可选 llama.cpp 本地服务入口 os/model/aiws-local-model.sh，镜像内路径 usr/local/bin/aiws-local-model，普通用户 systemd unit。必须在客体 VM 中运行、验证 guest 标记，使用仅客户机本地文件和 CPU 推理，监听 guest 127.0.0.1:18080，不自动下载模型，禁止主机 GPU/共享目录/管理接口。
新增 docs/AIWS_LOCAL_MODEL.md，明确模型作为结构化建议器、权限不来自模型、无云端 Token 默认工作流、微调数据与独立评测门槛。
文件：os/model/aiws-local-model.sh，os/debian/config/includes.chroot/usr/local/bin/aiws-local-model，os/debian/config/includes.chroot/etc/systemd/user/aiws-local-model.service，docs/AIWS_LOCAL_MODEL.md，本 routine。
验证：需运行 shell 语法和 OS 静态 CI，未训练或加载真实权重，显存消耗尚无实测。
下一步：模型意图数据集、训练数据验证、guest-only 评测、在 VM 中手动装载真实权重并测量、GUI 点击验收和 NixOS 镜像。
