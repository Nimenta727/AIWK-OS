namespace AIWorkstation.Core;

/// <summary>Read-only reconstruction of AIWS's local handoff draft, not provider-hidden context.</summary>
public static class ContextInspector
{
    public sealed record ContextPart(string Kind, string Title, int Characters, string Source,
        bool Included, string Evidence);
    public sealed record ContextReport(string StageId, int Characters, int OriginalCharacters,
        int SavedCharacters, int ApproxTokens, string Fingerprint, bool Truncated,
        string Text, IReadOnlyList<ContextPart> Parts, string Notice);

    public static ContextReport Preview(WorkTask task, WorkflowStep step)
    {
        var bundle = ContextCompiler.Compile(task, step);
        var parts = bundle.Manifest.Select(entry => new ContextPart(
            entry.Kind, entry.Reference, entry.Characters, "AIWS 本地工件清单",
            entry.Included, entry.Evidence)).ToList();
        parts.Add(new ContextPart("policy", "本地执行边界", 0,
            "AIWS 固定执行规范", true, "不授予额外 Windows 权限"));
        var handoff = new PreparedHandoff(bundle.Prompt, bundle.OriginalCharacters,
            bundle.SentCharacters, bundle.ApproxTokens, bundle.Fingerprint);
        const int maxPreview = 24_000;
        bool truncated = handoff.Text.Length > maxPreview;
        return new ContextReport(step.Id, handoff.SentCharacters, handoff.OriginalCharacters,
            handoff.SavedCharacters, handoff.ApproxTokens, handoff.Fingerprint, truncated,
            truncated ? handoff.Text[..maxPreview] : handoff.Text, parts,
            "仅展示 AIWS 在本地生成的交接草稿，不包含 Claude/Codex 自行附加的系统提示、MCP 工具声明、缓存或真实发送记录。字符估算不是计费用量。查看预览不会向模型发送请求。");
    }
}
