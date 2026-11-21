# AIWK-OS 0.2.0-preview.1 — 发行说明（草稿，未发布）

**定位**：面向程序员的 AI 原生操作系统。用自然语言驱动，首页是只读观察台；本地离线小模型做中转，云端通过官方 CLI 在你授权的范围内构建；开发者工具链预装，AIWS Code 编辑器随需打开。

> 这是**工程预览**。以下是发行时可以真实声明的内容，以及**不能**声明的内容。

## 可以声明（有测试或浏览器验证支撑）
- 观察台、审批 DAG、模型网关/路由/受约束输出、官方 CLI 监督器、出口代理、AIWS Code 启动接口的**代码与单元/契约测试**（Python 427 项、前端 70 项通过）。
- 前端在真实 Chromium 里走通：深/浅主题、标签页、命令面板、文件查看、面板切换。
- 开发者软件包名已对照真实 Debian 索引校验；预估安装体积约 +622 MB（闭包估算，非实测）。
- AIWS Code 的产品配置覆盖后，对 Microsoft 服务端点/品牌字符串的扫描结果为 0；webview 补丁可应用到固定上游版本。

## 不能声明（未验证）
- 实际构建出的 AIWS Code 能在镜像里运行、扩展兼容。
- 本地模型在真实客户机上的质量、内存与延迟；官方 CLI 的真实端到端运行。
- ISO 的体积、BIOS/UEFI/物理机启动、安装、Secure Boot；内核强制隔离。

## 发行前检查表
- [ ] CI：static、image-boot（BIOS/UEFI）、real-model 对目标提交全部成功（链接 Actions 运行）
- [ ] 实际执行 `os/ide/build-aiws-code.sh`，核对产物含上游 `LICENSE.txt` / `ThirdPartyNotices.txt` 与 `PROVENANCE.json`
- [ ] 在真实客户机里：打开 AIWS Code、观察台数据来自真实运行（非示例）、一次官方 CLI 授权构建（假/真各一次）
- [ ] `docs/THIRD_PARTY.md` 的「发行前仍需完成」五项
- [ ] 镜像 SHA-256 与 SBOM 随发行物发布；发行标记为 **pre-release**
- [ ] 仓库所有者确认：LICENSE/NOTICE 处理、是否对外分发 ISO

**发布规则**：不得在以上人工验收完成前把它称为稳定版；打 tag 与创建 GitHub Release 需要仓库所有者明确同意。
