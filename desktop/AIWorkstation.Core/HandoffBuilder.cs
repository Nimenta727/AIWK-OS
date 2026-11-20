namespace AIWorkstation.Core;

public sealed record PreparedHandoff(string Text, int OriginalCharacters, int SentCharacters, int ApproxTokens, string Fingerprint)
{
    public int SavedCharacters => Math.Max(0, OriginalCharacters - SentCharacters);
}

/// <summary>
/// Compatibility façade: preflight, inspector and actual launch all compile the
/// SAME deterministic prompt. The task context belongs to AIWS, not a provider chat.
/// </summary>
public static class HandoffBuilder
{
    public static string Build(WorkTask task, WorkflowStep step) => Prepare(task, step).Text;

    public static PreparedHandoff Prepare(WorkTask task, WorkflowStep step)
    {
        var bundle = ContextCompiler.Compile(task, step);
        return new PreparedHandoff(bundle.Prompt, bundle.OriginalCharacters,
            bundle.SentCharacters, bundle.ApproxTokens, bundle.Fingerprint);
    }
}
