# 第三方组件与许可 / Third-party components

> 本文件列出 AIWK-OS **构建或随镜像分发**的第三方组件及其许可类别。它是**人工整理的清单，不是自动生成的 SBOM**；
> 正式发行前必须用工具对最终镜像做完整依赖/许可审计（见下方「发行前仍需完成」）。

仓库自有代码遵循根目录 `LICENSE`（Apache-2.0）。下列组件保留各自许可，**重新品牌化或打包不改变其许可，也不去除署名**。

| 组件 | 用途 | 许可（上游声明） | 在本仓库中的处理 |
| --- | --- | --- | --- |
| Code - OSS（microsoft/vscode 源码） | AIWS Code 编辑器 | MIT，版权归 Microsoft Corporation 等 | 仅按固定提交在构建时获取；构建产物必须附带上游 `LICENSE.txt` 与 `ThirdPartyNotices.txt`（`build.sh` 缺失即拒绝）；不使用其商标、图标、市场、更新/遥测服务。见 `os/ide/NOTICE.md` |
| Open VSX（扩展注册表，服务端） | AIWS Code 的扩展来源 | 注册表由 Eclipse Foundation 运营；各扩展各有许可 | 仅作为可配置的网络端点；不内置任何扩展 |
| llama.cpp | 本地小模型推理 | MIT | 运行时按需获取/调用，不在仓库内 |
| Qwen3.5-2B（Alibaba Qwen，Q4_K_M GGUF 量化，来源 SoAIHQ/Qwen3.5-2B-GGUF） | 本地小模型 | **Apache-2.0**（2026-11-21 核对 Hugging Face 模型卡：原模型与 GGUF 仓库均声明 apache-2.0，原模型仓库含 Apache-2.0 LICENSE 全文） | 权重不入库；测试版 ISO 随附 `QWEN-LICENSE.txt` 并记录 sha256；量化版由第三方社区制作，仅按其声明的许可分发 |
| Debian 13 软件包（内核、gcc、Python、Node.js、Go、Rust、JDK、clang 等） | 系统与开发工具链 | 各包各自许可（GPL/LGPL/MPL/Apache/MIT 等混合） | 只写入**包名**，由构建时的 Debian 镜像下载；对外分发 ISO 前须满足源码提供等义务 |
| Linux 内核 | 系统内核 | GPL-2.0-only | 来自 Debian 包 |
| React、React DOM | 前端 | MIT | npm 依赖 |
| Vite、TypeScript | 前端构建 | MIT / Apache-2.0 | npm 开发依赖 |
| lucide-react | 图标 | ISC | npm 依赖 |
| @vscode/codicons 0.0.46-24 | 工作台图标字体（Microsoft） | 图标：CC-BY-4.0；其代码：MIT | npm 依赖，随前端打包。CC-BY-4.0 要求署名：“Codicons © Microsoft Corporation, CC BY 4.0, https://github.com/microsoft/vscode-codicons”；未修改字体。版本已固定（不用 `latest`）。 |
| xterm.js 及 fit 插件 | 终端界面 | MIT | npm 依赖 |
| Playwright | 浏览器自动化测试 | Apache-2.0 | 仅开发/测试依赖，不进入镜像 |
| poppler-utils（pdftotext）、pandoc | 文档阅读器与 `doc.text` 的转换 | GPL（poppler）/ GPL（pandoc）：通过 Debian 包安装、以独立进程调用，不链接进本项目代码 | 随 ISO 分发时须满足 GPL 的源码提供义务 |
| 字体（FiraCode、JetBrains Mono、Hack、Noto CJK 等） | 编程字体 | 各字体各自许可（多为 OFL） | Debian 包 |

> 上表中的许可类别来自对这些项目通行许可的了解，**未逐个对最终锁定版本的许可文件做自动核验**。

## 发行前仍需完成

1. 为前端补 `package-lock.json`，并对 npm 依赖树生成许可清单。
2. 对最终 ISO/镜像生成 SBOM（例如对 squashfs 内的 dpkg 数据库导出），核对每个包的许可与「是否需要提供源码」。
3. ~~模型权重许可~~ 已核对为 Apache-2.0（见上表）；仍应在每次更换权重/量化来源时重新核对。
4. ~~根 NOTICE~~ 已补（`NOTICE`）。仓库所有提交均来自仓库所有者的账户（含其委托的助手提交），LICENSE 由所有者本人于 2026-11-21 添加为 Apache-2.0，此前仓库内没有任何 LICENSE 文件，故不存在“已按 MIT 发布”的授权需要保留；README 中过去的 MIT 说法已更正。若将来接受外部贡献，需要贡献者协议或逐个确认授权。
5. 实际构建 AIWS Code 后，核对产物里确有上游 `LICENSE.txt` 与 `ThirdPartyNotices.txt`。
