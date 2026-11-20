# 2026-11-20_1533 — V1.4 windows-conpty-terminal

## 本次修改 / Changes
新增原生 ConPTY PowerShell 会话封装、xterm.js 离线终端、WebView2 事件桥接与启动确认；终端原始输入输出不写入模型和任务持久化。

## 涉及文件 / Files
ConPtyTerminal.cs, ModularWorkstationWindow.xaml.cs, TerminalPanel.tsx, bridge.ts

## 验证 / Verification
- 38 项 Python 回归测试本地通过。
- 13 项 Node 前端模型测试本地通过。
- .NET Windows 编译和原生 ConPTY GUI 操作需以 CI / Hyper-V 实测为准，不宣称当前已验收。

## 风险 / Known risks
- Windows 工作区验证不能替代沙箱；官方 CLI 继承当前用户权限。
- 模型内部调用与实际用量可能未知；不能把 CLI 启动当作模型调用。
- Git 的时间关联并不能独立证明某次文件改动由 Agent 写入。

## 下一步 / Next steps
下一步在 Hyper-V Windows VM 验证 PTY 生命周期、中文字符、调整尺寸与结束行为；没有 OS 沙箱。
