"""Deterministic agent recommendation. No model credentials are accessed."""

CLAUDE_HINTS = ("架构", "方案", "设计", "规划", "分析", "研究", "解释", "architecture", "design", "research", "planning")
CODEX_HINTS = ("代码", "实现", "修复", "测试", "重构", "bug", "coding", "implement", "fix", "refactor", "test")


def recommend(title: str, description: str) -> dict:
    content = f"{title} {description}".lower()
    c = sum(1 for word in CLAUDE_HINTS if word in content)
    x = sum(1 for word in CODEX_HINTS if word in content)
    if c >= 1 and x >= 1:
        return {"agent": "dual", "reason": "任务同时涉及方案分析与代码执行；建议分阶段交接，并人工审查。"}
    if c > x:
        return {"agent": "claude", "reason": "偏分析、规划或研究；建议先用 Claude Code。"}
    if x > c:
        return {"agent": "codex", "reason": "偏代码实现、重构或测试；建议先用 Codex。"}
    return {"agent": "manual", "reason": "未识别到可靠任务类型，请手动选择执行器。"}
