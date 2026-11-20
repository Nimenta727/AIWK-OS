namespace AIWorkstation.Core;

/// <summary>
/// AIWS-owned preflight for the exact local handoff draft. This is an approximate
/// prompt-size gate, NOT a provider token limit: external interactive CLIs can
/// add system instructions, tool outputs and extra requests after launch.
/// No remote inference or provider credential is used by this policy.
/// </summary>
public static class ContextBudgetPolicy
{
    public const int DefaultWarningTokens = 2500;
    public const int DefaultStopTokens = 6000;
    public const int MinimumWarningTokens = 500;
    public const int MaximumStopTokens = 50000;

    public sealed record Assessment(
        int ApproxTokens, int WarningTokens, int StopTokens,
        int OriginalCharacters, int SentCharacters, int SavedCharacters,
        bool Warn, bool Blocked, bool Duplicate,
        string Note);

    public static void Validate(int warningTokens, int stopTokens)
    {
        if (warningTokens < MinimumWarningTokens || stopTokens > MaximumStopTokens ||
            stopTokens <= warningTokens)
            throw new ArgumentOutOfRangeException(nameof(stopTokens),
                $"交接预算须满足 {MinimumWarningTokens} ≤ 提醒阈值 < 拦截阈值 ≤ {MaximumStopTokens}。两者都是本地估算值，不是模型计费上限。");
    }

    public static Assessment Assess(WorkTask task, WorkflowStep step)
    {
        ArgumentNullException.ThrowIfNull(task);
        ArgumentNullException.ThrowIfNull(step);
        if (step.Agent == AgentKind.Manual)
            throw new InvalidOperationException("人工阶段不产生 AIWS 模型交接提示词。");
        Validate(task.PromptWarningTokens, task.PromptStopTokens);
        var prepared = HandoffBuilder.Prepare(task, step);
        var duplicate = !string.IsNullOrWhiteSpace(step.LastPromptFingerprint) &&
            string.Equals(step.LastPromptFingerprint, prepared.Fingerprint, StringComparison.Ordinal);
        var blocked = prepared.ApproxTokens > task.PromptStopTokens;
        var warn = prepared.ApproxTokens > task.PromptWarningTokens || duplicate;
        var note = blocked
            ? "本地交接草稿超过任务配置的估算上限：请精简任务指令或显式调整预算；尚未复制提示词或启动 CLI。"
            : duplicate
                ? "与该阶段上次准备的提示词完全相同。重试前请核对是否确有必要；需要原生窗口额外确认。"
                : warn
                    ? "本地交接草稿接近较大规模：建议去除重复上下文；启动前仍需用户确认。"
                    : "本地交接草稿位于配置范围内；不会自动调用模型。";
        return new Assessment(prepared.ApproxTokens, task.PromptWarningTokens, task.PromptStopTokens,
            prepared.OriginalCharacters, prepared.SentCharacters, prepared.SavedCharacters,
            warn, blocked, duplicate, note);
    }

    public static void RequireAllowed(WorkTask task, WorkflowStep step, bool confirmDuplicate = false)
    {
        var check = Assess(task, step);
        if (check.Blocked)
            throw new InvalidOperationException($"本地提示词预估 {check.ApproxTokens} Token，超过本任务拦截阈值 {check.StopTokens}。请调整上下文或预算后重新启动。");
        if (check.Duplicate && !confirmDuplicate)
            throw new InvalidOperationException("同阶段提示词重复：需要额外确认才能再次启动。未复制内容或启动 CLI。");
    }
}
