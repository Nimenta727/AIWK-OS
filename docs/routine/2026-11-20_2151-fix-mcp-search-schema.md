# 2026-11-20 21:51 · MCP code.search optional path correction

## 中文
**变更摘要：** 修正 MCP 工具声明中的 code.search 参数规则：query 是必填，path 是可选，默认从选定工作区搜索。原声明错误地把 path 也设成必填，导致离线静态测试在该场景失败。保留参数白名单和路径约束。

**影响文件：** os/runtime/aiws_toolplane.py；本 routine 日志。

**验证：** 通过 GitHub Actions 运行 Python unittest；本次代码提交时上一个 CI 在 11 个测试中通过了 10 个，其余由于此参数错误失败，修复版尚需重新检查 Actions 结果。不等于已验证 ISO 或真实浏览器。

**已知限制：** 尚无真正构建/启动的独立 ISO；MCP 实验性实现、浏览器与权限边界仍需要系统级验证。

**下一步：** 重新验证 AIWS OS static CI；运行安装镜像、工具协议连通性及宿主隔离测试。

## English
Fix inputSchema for code.search: query is required, optional path defaults to workspace root. Previous CI failed this case. Pending a fresh CI run; no ISO or browser runtime verification implied.
