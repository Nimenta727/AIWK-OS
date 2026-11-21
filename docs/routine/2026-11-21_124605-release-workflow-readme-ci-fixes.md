# 2026-11-21 · 发行工作流、README 重写、CI 修复

## 做了什么
- **发现并修复 CI 失败**：GitHub 上“静态契约”工作流在最近几次提交失败（runner 没有 Pillow；nft 规则校验在 runner 上没有 CAP_NET_ADMIN）。测试现在对这两种环境限制明确跳过；工作流安装 Pillow、并新增前端 `tsc` + node 测试步骤。
- **发行工作流 `release-preview.yml`**：三个作业——构建 AIWS Code（固定上游提交，传入 `GITHUB_TOKEN` 供其依赖下载 GitHub 发行物）、在 Debian 13 容器里编译固定提交的 llama-server、构建完整 ISO（`AIWS_OS_PROFILE=full` + AIWS Code + 模型权重）→ 在 QEMU 里启动并要求 `AIWS_BOOT_SMOKE_PASS` → 拆分成 ≤1.9 GiB 分卷（GitHub 附件上限 2 GiB）→ 生成 SHA256SUMS、重组说明、发行说明 → **仅在 `stage=full` 且前面全部通过时**发布 pre-release。`release/PREVIEW.env` 控制阶段：`code`（只构建 AIWS Code 与 llama-server）/ `iso-dry`（再构建 ISO 并启动，不发布）/ `full`（发布）。
- **模型权重许可**：核对 Hugging Face 模型卡——Qwen3.5-2B 与 GGUF 仓库均声明 Apache-2.0，原模型仓库含 Apache-2.0 全文；`THIRD_PARTY.md` 已更新；发行物随附 `QWEN-LICENSE.txt`、记录权重 sha256。
- **README 重写**（去掉 Windows 部分，新增“试用测试版 ISO”“自己构建”“仓库地图”）。

## 验证 / 限制
- Python 438 项通过（2 项因环境限制跳过）。工作流 YAML 语法通过。
- **AIWS Code 的真实构建无法在本沙箱完成**：沙箱不允许下载其依赖（`@vscode/ripgrep` 从 GitHub 发行物下载）。已在本沙箱里确认：克隆固定提交、产品覆盖、补丁应用、`pnpm install` 的原生模块编译（含 sqlite3）都成功，卡在 ripgrep 下载。其余由 Actions 验证。

## 下一步
1. 推送后先跑 `stage=code`，看 AIWS Code 是否真能构建；失败就按日志修。
2. 再跑 `iso-dry` 验证 ISO 构建与启动；最后 `full` 发布。
