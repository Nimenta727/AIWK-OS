# 2026-11-23 13:28 — 工作台路由表 + 两个大文件按功能拆分

## 背景
上一轮审计留下的两项结构问题，用户要求"先修完结构"：
1. 工作台 POST 路由是一长串字符串加条件判断，难维护，又是安全入口。
2. `aiws_workbench.py`（1,160 行）、`aiws_toolplane.py`（800 行）偏大。

第三项（38 处 `raise ... from`）只影响报错时的调用链显示，本次没有做。

## 做了什么

### 1. 显式路由表（新文件 `os/runtime/aiws_workbench_http.py`，555 行）
- `GET_ROUTES`（36 条）和 `POST_ROUTES`（33 条）是写在一处的表。`{name}` 段匹配一个非空段，作为参数传给处理函数；其他段必须逐字相同。只去掉开头一个 `/`，所以 `/api/v1/tasks/` 这种带尾斜杠的路径不会意外匹配。
- POST 的检查顺序和以前完全一样：Host → **不在表里直接 404**（先于其他检查）→ Origin → CSRF（常数时间比较）→ JSON 类型 → 0 < 长度 ≤ 16 KiB → 必须是 JSON 对象 → 各路由自己的字段检查 → 统一的异常→状态码映射。
- 原来 `do_GET` 里每个分支重复的"走 Agent 服务或本地调用、审计、错误映射"合并成 `_plane_read` 等几个小函数。原来 `/workspace/file` 漏了 `AgentUnavailable` 的处理（会变成 500），现在和其他读取一样返回 503。
- 文件顶部写明每个请求经过的检查链。

### 2. `aiws_workbench.py`：1,160 → 728 行
- 只保留应用层：Controller、`make_server`、`main`。
- 新增 `Controller.route_config()`，让 HTTP 层不直接调用配置加载，测试里对 `aiws_workbench.load_config` 的打桩继续有效。
- `Handler`、`HOST`、`EXPOSED`、`ASSETS` 从新模块再导出，原有的 `from aiws_workbench import make_server, HOST` 不用改。

### 3. `aiws_toolplane.py`：800 → 200 行，拆成三个
| 文件 | 行数 | 内容 |
|---|---|---|
| `aiws_toolplane.py` | 200 | 契约：工具清单、类别、`_workspace`/`_path` 路径约束、参数检查、`invoke` 分发、审计 |
| `aiws_tools_files.py` | 330 | 文件类：读、改、stat、建目录、复制/移动/回收站/恢复、目录树、搜索、日志摘要、文档文本 |
| `aiws_tools_system.py` | 300 | 系统类：系统/网络状态、下载、git、运行时、本地浏览器文本 |

- 分发从一串 `if name == ...` 改成一张表，**第一次调用时**才建（工具模块要从核心模块导入辅助函数，这样不会循环导入）。我核对过：清单里每个工具都有处理函数（`app.launch` 按设计拒绝），扩展工具没有重名。
- 路径约束留在核心模块。12 个测试在 `aiws_toolplane.protect_guest_workspace` 上打桩，拆分后依然生效。
- 两个新模块已加入 `os/runtime/MODULES`，镜像构建会自动带上。

### 4. 测试
- 新增 `os/verify/test_workbench_routes.py`（7 项）：
  - 表里没有重复，也没有被前面规则挡住的规则。
  - 匹配是精确的（尾斜杠、空段、未知动作、大小写、`..` 都不匹配）。
  - **前端代码里出现的每个 API 路径都在表里**（扫描 `workbench/src`，防止前后端不一致）。
  - 真实服务器上：表外路径对 GET 和 POST 都是 404，且 POST 的 404 先于 CSRF 检查。
  - **对表里每一条 POST 路由**，错误的 CSRF、缺少 CSRF、外来 Origin、非 JSON、空请求体、非对象请求体都被拒绝。
  - Host 不对时两种方法都拒绝；正常请求仍然能用。
- **变异检验**：删掉一条前端在用的路由 → 前后端一致性测试失败；去掉 CSRF 检查 → CSRF 测试失败。
- 两个读源码的测试（错误文案翻译覆盖、镜像打包检查）改为同时读取两个工作台文件，并断言确实读到了 HTTP 层。
- 网络解析测试改为在 `aiws_tools_system` 上打桩。

## 涉及文件
- 新增：`os/runtime/aiws_workbench_http.py`、`os/runtime/aiws_tools_files.py`、`os/runtime/aiws_tools_system.py`、`os/verify/test_workbench_routes.py`。
- 修改：`os/runtime/aiws_workbench.py`、`os/runtime/aiws_toolplane.py`、`os/runtime/MODULES`、`os/runtime/README.md`、`docs/CODEBASE_MAP.md`、`os/verify/test_error_translations.py`、`os/verify/test_router.py`、`os/verify/test_stage3.py`。

## 验证
- Python 全量：**925 通过，2 跳过**（918 + 新增 7）。
- `ruff check --select F,E9,PLE` 全仓库通过。
- 对外行为（状态码、错误文字、检查顺序）不变，唯一差别是上面那处 503。

## 已知问题
- 没有在镜像里启动验证；镜像在构建时从 `MODULES` 取文件，打包测试已覆盖新文件。
- `Controller`（约 620 行）仍是一个类，可按领域再拆（构建 / 模型 / IDE·预览 / 任务），这次没动。
- 38 处 `raise ... from` 未改。

## 下一步
1. 如果需要：把 Controller 按领域拆成几个小类，HTTP 层按领域引用。
2. 补 `raise ... from`，然后把 ruff 的 B 规则加进 CI。
3. 仍待你同意：手动跑一次镜像启动验收（验证启动菜单修复），以及让镜像测试在 PR 阶段运行。
