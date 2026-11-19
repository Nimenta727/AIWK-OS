"""Local workflow templates inspired by agent control-plane patterns.

This is independent code, not a copy of T3 Code or Kandev internals.
Execution is explicitly user-driven; a planned step does not grant CLI access.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StepTemplate:
    agent: str
    name: str
    instructions: str


def plan_for(agent: str) -> tuple[StepTemplate, ...]:
    if agent == "dual":
        return (
            StepTemplate("claude", "方案与风险分析", "检查需求和现有代码；设计实施步骤、测试方案及潜在风险。不得修改文件。"),
            StepTemplate("codex", "受控实现与测试", "根据前一阶段的方案，在用户同意的项目范围内实现并测试。将变更写入 docs/routine/。"),
            StepTemplate("claude", "独立复核", "复核上一阶段修改和测试记录，指出遗漏、风险、回归问题；不得自行推送代码。"),
        )
    if agent == "claude":
        return (StepTemplate("claude", "Claude 处理", "围绕用户目标完成当前任务。任何文件修改和外部操作需遵守项目权限及审批要求。"),)
    if agent == "codex":
        return (StepTemplate("codex", "Codex 处理", "围绕用户目标完成当前任务。任何文件修改和外部操作需遵守项目权限及审批要求。"),)
    if agent == "manual":
        return (StepTemplate("manual", "人工选择执行器", "由用户选择官方 CLI 处理当前任务，并记录实际使用的 Agent 与结果。"),)
    raise ValueError("未知 Agent")
