namespace AIWorkstation.Core;

/// <summary>
/// Capability contracts for separately installed, interactive official CLIs.
/// Describes what AIWS can actually observe. No subscription credential is read
/// or exchanged, and this registry never sends a model request.
/// </summary>
public sealed record ProviderCapability(
    string Id, string Name, AgentKind Agent, string ToolName,
    bool Available, bool RequiresUserLaunch, bool SupportsUnattended,
    bool SupportsLocalWorktree, bool CanImportStructuredUsage,
    bool CanObserveInternalRequests, string Notice);

public static class ProviderAdapterRegistry
{
    public static string IdFor(AgentKind kind) => kind switch
    {
        AgentKind.ClaudeCode => "claude-cli",
        AgentKind.Codex => "codex-cli",
        AgentKind.Manual => "manual",
        _ => throw new ArgumentOutOfRangeException(nameof(kind))
    };

    public static IReadOnlyList<ProviderCapability> Describe(Func<string, bool>? isInstalled = null)
    {
        isInstalled ??= tool => AgentTools.Locate(tool) is not null;
        return
        [
            new("claude-cli", "Claude Code", AgentKind.ClaudeCode, "claude", isInstalled("claude"), true,
                false, true, true, false,
                "官方交互式 CLI：仅能记录启动意图；需要明确选择的官方结构化日志才能导入用量。"),
            new("codex-cli", "Codex CLI", AgentKind.Codex, "codex", isInstalled("codex"), true,
                false, true, true, false,
                "官方交互式 CLI：本集成不承诺无人值守；内部请求与实际计费不可完全观测。"),
            new("manual", "人工验收", AgentKind.Manual, "", true, false,
                false, true, false, false,
                "不会启动模型，也不会产生 AIWS 侧模型请求。")
        ];
    }

    public static ProviderCapability For(AgentKind kind, Func<string, bool>? isInstalled = null) =>
        Describe(isInstalled).Single(c => c.Agent == kind);

    public static void EnsureSwitchable(WorkTask task, WorkflowStep step, AgentKind target)
    {
        if (!Enum.IsDefined(target)) throw new ArgumentException("未知执行器。", nameof(target));
        if (!task.Steps.Contains(step) || step.Status != StepStatus.Pending ||
            !string.IsNullOrWhiteSpace(step.RunId) || step.StartedAt is not null)
            throw new InvalidOperationException("只能切换尚未启动过的阶段，避免破坏运行审计链。");
    }
}
