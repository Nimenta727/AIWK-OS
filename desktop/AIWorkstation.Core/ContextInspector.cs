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
        var handoff = HandoffBuilder.Prepare(task, step);
        var index = task.Steps.IndexOf(step);
        if (index < 0) throw new ArgumentException("未知阶段。");
        var history = (task.GraphMode ? task.Steps.Where(x => step.DependsOn.Contains(x.Id)) :
            task.Steps.Take(index)).Where(x => x.Status == StepStatus.Completed).ToList();
        var parts = new List<ContextPart>
        {
            new("metadata", "阶段标题与执行器", task.Title.Length + step.Title.Length + AgentLabel.Name(step.Agent).Length,
                "AIWS 工作流配置", true, "本地可见；仅字符统计"),
            new("instructions", "当前阶段原始指令", step.Instructions.Length,
                "用户指定的阶段指令", true, "不静默截断当前指令")
        };
        var included = history.TakeLast(2).ToList();
        var already = new HashSet<string>(StringComparer.Ordinal);
        foreach (var previous in included)
        {
            var result = previous.Result.Trim();
            var unique = already.Add(result);
            parts.Add(new ContextPart("handoff", previous.Title, unique ? Math.Min(result.Length, 1200) : 0,
                "已完成阶段的人工记录结果", unique, unique ? result.Length > 1200 ? "超过 1200 字符，已截断" : "已引用" : "重复结果被省略"));
        }
        if (history.Count > 2)
            parts.Add(new ContextPart("omitted", "早期阶段结果", 0, "已完成阶段历史", false,
                $"另外 {history.Count - 2} 个早期阶段未加入交接"));
        parts.Add(new ContextPart("policy", "本地执行边界", 0, "AIWS 固定提示规范", true,
            "不可自动推送或访问未授权目录；字符已计入预览总数"));
        const int maxPreview = 24_000;
        bool truncated = handoff.Text.Length > maxPreview;
        return new ContextReport(step.Id, handoff.SentCharacters, handoff.OriginalCharacters,
            handoff.SavedCharacters, handoff.ApproxTokens, handoff.Fingerprint, truncated,
            truncated ? handoff.Text[..maxPreview] : handoff.Text, parts,
            "仅展示 AIWS 在本地生成的交接草稿，不包含 Claude/Codex 自行附加的系统提示、MCP 工具声明、缓存或真实发送记录。字符估算不是计费用量。查看预览不会向模型发送请求。");
    }
}
