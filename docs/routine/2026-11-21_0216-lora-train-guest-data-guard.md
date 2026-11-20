# 2026-11-21 02:16 — Ensure trainer refuses host dataset access

## 修复
修正可选 LoRA 训练入口：原先在虚拟机校验前先读取 --dataset，存在误运行时读取非客户机任意文件的风险。现默认非训练 dry-run 只能检查打包的合成数据；--train-in-guest 必须先通过非 root/guest marker/VM 检测，再限定训练数据在客户机个人 AIWS training 目录、拒绝共享挂载，才读取样本。
## 文件
os/model/training/train_lora.py、本 routine。
## 测试
提交后需运行 OS CI dry-run 和样本 schema 检查。未下载/训练任何模型，训练依赖兼容性及 2B 资源占用尚未测量。未来真实训练仍必须在客户机内得到明确授权并审查数据来源。
## 下一步
将受控数据导入客户机，先跑未微调模型的真实离线评测，再按效果决定 LoRA；继续 GUI real VM 和任务/DAG 回归。
