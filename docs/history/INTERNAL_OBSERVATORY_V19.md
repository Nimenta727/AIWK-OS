# V1.9 Internal Observatory / 内部执行透视

## 中文
新版将任务阶段、DAG 依赖、上下文来源清单、Token 用量证据、阶段事件和 Git 结构变化汇入同一只读面板。选中阶段后，可以切换“项目结构变化”“上下文来源”“执行事件”，展开目录，点文件查看 Diff；亦可跳转计划中心、执行全景与阶段检查器。主导航与新视图支持中文 / English 切换。
技术边界：阶段或 CLI 启动不代表远程模型请求。没有官方结构化日志时 Token 必须显示未知；结构检查点不完整时不能断言没有变化。纯本地视图不触发模型请求。旧页面有部分中文文案，完整界面本地化尚未完成。
测试目标：Node 本地投影逻辑、Edge Playwright 实际点击、Windows WPF/.NET 构建、Hyper-V GUI 分别验证。

## English
The Internal Observatory combines persisted task stages, DAG dependencies, context provenance, evidence-backed usage, execution events and Git directory diffs in one read-only surface. Select a stage, switch between project impact, context and events, expand a changed folder, or open a file diff; navigate to the existing Plan Studio, Execution Atlas and stage inspector.
**Evidence boundary:** CLI launch or stage status does not prove a provider model request. Missing usage and incomplete Git checkpoints must remain explicitly unknown. Opening this local view never invokes a model. The new surface and primary navigation offer Chinese/English switching; legacy panels still have untranslated copy.
Quality gates: Node model tests, Playwright Edge interactions, Windows desktop CI and separate Hyper-V GUI verification.
