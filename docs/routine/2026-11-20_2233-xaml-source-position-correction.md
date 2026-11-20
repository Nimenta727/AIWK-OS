# 2026-11-20 22:33 · XAML binding position extraction correction

## 中文
**变更：** 修复前一提交生成的 XAML 原始字符串正则转义；改成先以 XML parser 验证 x:Class 属性，再按实际字面属性标记定位，消除多层转义造成的匹配错误。仍是静态候选位置，不声称语言服务器语义验证。
**文件：** os/runtime/aiws_codeintel.py, 本 routine。
**验证：** 准备交由 GitHub Actions 实测，旧规则未作为通过依据。
**限制：** 当前源码位置解析只支持常规单双引号属性格式；对复杂 XML 格式应保留未识别而非编造定位。
**下一步：** 核查回归测试及构建门槛、进一步补充 AST/LSP 后端测试、镜像实测。

## English
Correct the escaping-sensitive XAML source-position matcher; use validated XML root attributes followed by exact attribute-string positioning. Re-run CI and retain unverified semantic evidence.
