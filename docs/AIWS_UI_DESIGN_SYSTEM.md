# 工作台界面规范（2026-11-22）

目标：像编辑器一样可靠、克制、可键盘操作；每个控件只有一种长相、一种光标、一套状态。代码在 `workbench/src/ui/`，页面在 `workbench/src/app/`。

## 令牌（`ui/tokens.css`）
颜色、字号、间距、光标全部来自变量，深色/浅色两套，色值取自 VS Code Dark Modern / Light Modern。页面里不允许写死颜色。

## 光标（`ui/base.css`，一处定义）
| 对象 | 光标 |
| --- | --- |
| 按钮、标签页、列表行、链接、下拉、复选框 | `pointer` |
| 禁用控件 | `default`（同 VS Code），透明度 .4 |
| 文本输入 | `text`；界面文字默认不可选，内容区（`.selectable`）可选 |
| 分隔条 | `ew-resize` / `ns-resize`；拖动中全局锁定该光标 |
| 可拖拽元素 | `grab` / `grabbing` |
| 忙碌 | `progress` |

## 状态
默认、悬停、按下、键盘聚焦（1px 聚焦环，仅键盘触发）、禁用、选中。图标按钮必须带 `label`（同时是提示和无障碍名称）。

## 键盘
Ctrl+Shift+P / F1 命令面板，Ctrl+B 侧栏，Ctrl+J 面板，Alt+W 关标签，Alt+←/→ 切标签；分隔条可用方向键调整（Shift 加速）；弹窗 Esc 取消，焦点先落在安全选项上。

## 组件（`ui/kit.tsx`、`ui/Layout.tsx`）
Button、IconButton、Badge、Input、Select、Check、Progress、Section、Row、Empty、Notice；ActivityBar、SideBar、Tabs、BottomPanel、StatusBar、Palette、Dialog、Sash。

## 图标许可
Codicons：图标 CC-BY-4.0（需署名，已写入 `NOTICE` 与 `docs/THIRD_PARTY.md`），版本固定为 0.0.46-24。

## 遗留页面
「AI 文件管理」「持久任务与 DAG」「本地 AI 助手」「系统服务与内核」仍是旧组件，只做了颜色变量映射以便外观一致；它们尚未按本规范重写（见 routine 日志）。
