# 2026-11-21 · 代码结构整理、README 重写与发行准备

## 做了什么
- **运行时模块清单**：新增 `os/runtime/MODULES`，`build.sh` 改为逐行读取清单拷贝（取代 24 个文件名的手写长 `cp`）；新增 `test_runtime_manifest.py`（清单与目录必须一致、清单无重复、`build.sh` 只拷贝 `aiws_*.py` 形态的名字）；`os/verify/buildsrc.py` 让原有 5 个静态测试继续检查“镜像是否装入了某模块”。
- **README 重写**：突出定位——面向程序员的 AI 原生系统；自然语言驱动；首页是只读观察台；本地离线小模型中转；官方 CLI 云端构建；开发者工具链 + AIWS Code；并加入“现在到了哪一步”的如实状态表。
- **文档**：更新 `CODEBASE_MAP.md`（新目录、新模块、前端结构）、`docs/README.md` 索引；新增 `CHANGELOG.md`、`docs/THIRD_PARTY.md`（人工整理的第三方清单 + 发行前审计项）、`docs/RELEASE_NOTES_OS_PREVIEW.md`（草稿，含“可声明/不可声明”与检查表）、`os/VERSION`（0.2.0-preview.1）。
- **许可证表述纠偏**：`LICENSE` 文件实际是 Apache-2.0，但 README、`os/README.md`、`os/ide/NOTICE.md`、`CODEBASE_MAP.md` 写的是 MIT，已改为与 LICENSE 一致；`AIWS_OS_BLUEPRINT.md` 中关于迁移的待办保留并更新措辞。

## 验证
- Python 全量 382 项通过（2 项跳过）；`bash -n build.sh` 通过；单独运行了清单拷贝循环，确实装入 24 个模块。
- README 中的语言/工具清单已逐项对照包清单（修正了写错的 Gradle、Swift，以及不存在的 `npm ci`/文档指向）。

## 已知问题 / 需要你决定
- **许可证**：根 `LICENSE` 是标准 Apache-2.0 文本，没有填写版权人，也没有根 `NOTICE`；此前是 MIT。是否有他人贡献、旧 MIT 代码如何处理，需要仓库所有者确认（`THIRD_PARTY.md` 已列为发行前事项）。
- 第三方清单里的许可类别是人工整理，未逐个自动核验；模型权重许可必须逐项确认。
- 前端没有 `package-lock.json`；旧目录（`aiws/`、`web/`、`app.py`、`tests/`）仍被 CI 引用，本次没有移动。
- `os/model/aiws-local-model.sh` 与镜像内安装的 `aiws-local-model` 是否漂移尚未核对。

## 下一步
1. 你确认许可证处理后，补根 `NOTICE` 与 LICENSE 版权行。
2. 实际执行 `os/ide/build-aiws-code.sh`（需要较大下载与构建时间）并核对许可文件；再嵌入镜像构建。
3. 补 `package-lock.json`，生成 SBOM。
4. 触发/查看 CI 结果；全部满足检查表后，**由你决定**是否打 tag 并创建 pre-release（我不会擅自发布）。
