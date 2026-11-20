# 2026-11-20 17:20 — 计划中心 Windows CI 与版本元数据核对

## 本次变更
- 核对 GitHub 原生 Windows 构建 Actions 44708213179：React、WPF/.NET、核心行为测试及 EXE ZIP 打包成功。
- 核对回归 Actions 44708213271：全部成功。
- 核验实际下载的 CI 产物：有 EXE、`ui-dist/index.html`，且编译前端包含「计划中心」。
- 修正 `desktop/AIWorkstation.Desktop/AIWorkstation.Desktop.csproj` 的版本元数据，使 Windows EXE 版本与 Plan Studio V1.7.1 一致。
- 更新 `README.md` 和 `docs/PLAN_STUDIO_V171.md` 中的验收说明。

## 影响文件
- `desktop/AIWorkstation.Desktop/AIWorkstation.Desktop.csproj`
- `docs/PLAN_STUDIO_V171.md`
- `README.md`
- `docs/routine/2026-11-20_1720-plan-studio-ci-verification.md`

## 已验证 / 待验证
- 原生 CI 已验证初次 V1.7.1 功能提交 2ccc795182dc6c3413564515703a31ee467f592d。
- 此次版本元数据修正需要重新编译通过并使用更新后的产物；不能以先前 CI 直接证明新的 commit。
- Hyper-V 实机的窗口、文件监测、Unicode 输入、性能、异常恢复仍未验收。

## 下一步规划
1. 等待本次元数据修正后的原生 Windows CI，检查构建产物一致性。
2. 在实际 Hyper-V VM 验证文件热更新和真实工作流阶段变化。
3. 设计支持手动粘贴计划、历史计划比较、计划与 Agent 事件稳定 ID 的独立迭代。
4. 对可观察的数据明确证据来源，禁止把 CLI 内部未知请求填成已成功。
