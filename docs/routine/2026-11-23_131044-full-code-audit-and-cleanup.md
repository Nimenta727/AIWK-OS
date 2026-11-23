# 2026-11-23 13:10 — 全项目代码审计与优化

## 背景
用户："把这个项目所有的代码都审计同时优化一下"。
仓库规模：Python 约 27,300 行（运行时 `os/runtime` 约 12,700 行，其余主要是测试），前端 TS/TSX 约 2,000 行，Shell 约 530 行，工作流 4 个。

## 怎么审的
1. **工具全量扫描**（覆盖每个文件）
   - Python：`ruff`（pyflakes 未定义名/未用、bugbear、错误级规则）、`bandit`（安全，中危以上）、`vulture`（死代码）。
   - Shell：`shellcheck -S warning`，覆盖所有 `.sh`、镜像内 `/usr/local/bin/*` 和 live-build 钩子。
   - 前端：`tsc --noUnusedLocals --noUnusedParameters`、`npm audit`，以及从入口算一遍可达文件。
2. **人工审阅安全边界**：工作区路径解析（`aiws_toolplane._path`）、预览服务器（`aiws_preview.resolve`）、工作台 HTTP 服务（Host/Origin/CSRF/大小/类型检查、静态资源路径）、各处 SQL 拼接、构建工具的临时目录。
3. **查数据库查询对应的索引**。

## 结论（重点）
- **没有发现可利用的安全漏洞，也没有会导致运行错误的缺陷**：没有未定义名、没有语法错误；依赖 0 个已知漏洞。
- 路径解析：逐段拒绝符号链接、拒绝 `..`/`.git`/`.ssh`，再用 `resolve()` + `is_relative_to` 复核。
- 工作台服务：只绑 127.0.0.1，同时检查 Host（防 DNS 重绑定）、Origin、CSRF 头、`application/json`、16 KB 上限。
- bandit 报的 SQL 拼接都是**白名单列名或固定占位符**，`/tmp` 告警实际用的是 `mkdtemp`：均为误报。
- 真正的问题都是**卫生和可维护性**层面，下面已全部修掉。

## 改了什么
| 类别 | 内容 |
|---|---|
| 死代码 | 删 41 个未用导入；删 4 个没人用的常量（`GUEST_WRITES`、`LEGACY_NAME_RE`、`MARKER_RE`、`TIERS_FOR_OVERRIDE`）；`LocalAgent` 删掉一个**接收了但从不使用**的参数 `retrieval_extra`（调用方会误以为它生效） |
| 测试质量 | 4 处测试里的未用变量。其中 `test_the_skill_brings_its_tools_into_view` 先记下"之前可见的工具"却没断言，**测试其实没证明标题说的事**；已补上断言（日志工具之前不可见、加载技能后才可见），并通过 |
| 性能 | 补 3 个 SQLite 索引：`stages(created_at)`（权限中介每次写操作都按时间窗口统计，原来全表扫描且表只增不减）、`sessions(started)`、`runs(started)`（列表和清理都按它排序）。`IF NOT EXISTS`，旧数据库启动时自动补上 |
| 加固 | CSRF 头比较改为 `secrets.compare_digest`（常数时间） |
| Shell | 修完全部 shellcheck 警告：未用的循环变量；`mkdir -p -m 0700` 只对最深一层生效 → 改为先建目录再 `chmod 0700 "$state"` |
| 前端 | 去掉两个组件里没用的 `english` 属性；`tsconfig` 打开 `noUnusedLocals`/`noUnusedParameters`；包版本 0.2.0 → 0.3.0-preview.1，与发布对齐 |
| CI | 静态工作流新增"Lint"步骤：`ruff`（F/E9/PLE）+ `shellcheck`。以后再出现未定义名、未用导入或 shell 警告，推送时就会红 |

共 52 个文件，+35 / −64 行，不改变任何功能行为。

## 验证
- Python 全量：**918 通过，2 跳过**（改动前后一致）。
- 前端：严格 `tsc` 通过，`vite build` 通过，45 项单元测试通过；`npm audit` 0 个漏洞。
- `ruff check --select F,E9,PLE` 全仓库通过；`shellcheck -S warning` 全部 shell 通过。

## 有意没改的（以及原因）
- **38 处 `raise ... from`（B904）**：只影响异常链的显示，不影响行为；改动面大、收益小。
- **工作台 POST 路由**是一长串字符串加两条条件，可读性差。重构成路由表收益明显，但这是安全入口，应单独做并配专门测试，没有混在这次清理里。
- `aiws_workbench.py`（1,160 行）、`aiws_toolplane.py`（800 行）偏大，可按功能拆分；同样建议单独做。
- 训练脚本 `os/model/training/` 的 HuggingFace 下载未固定 revision（bandit B615）：不进镜像，仅离线实验用。

## 下一步
1. 把工作台 POST 路由改成显式路由表，并为"未列出的路径一律 404"加测试。
2. 拆分 `aiws_workbench.py`（HTTP 层 / 应用状态 / 各功能端点）。
3. 逐步给 `raise` 补 `from`，并把 ruff 的 B 规则加进 CI。
4. 上一份日志里的 CI 事项（手动跑一次镜像启动验收、PR 上跑镜像测试）仍待你同意。
