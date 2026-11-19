using System.Text;

namespace AIWorkstation.Core;

public sealed record PreparedHandoff(string Text, int OriginalCharacters, int SentCharacters, int ApproxTokens, string Fingerprint)
{
    public int SavedCharacters => Math.Max(0, OriginalCharacters - SentCharacters);
}

public static class HandoffBuilder
{
    // A deterministic budget on handoff history, not an exact token cap or a provider model limit.
    private const int MaxPreviousResults = 2;
    private const int MaxResultChars = 1200;

    public static string Build(WorkTask task, WorkflowStep step) => Prepare(task, step).Text;

    public static PreparedHandoff Prepare(WorkTask task, WorkflowStep step)
    {
        var index = task.Steps.IndexOf(step);
        if (index < 0) throw new ArgumentException("阶段不属于当前任务。");
        var history = task.Steps.Take(index).Where(x => x.Status == StepStatus.Completed).ToList();
        var sb = new StringBuilder();
        sb.AppendLine($"# {task.Title}");
        sb.AppendLine($"阶段 {index + 1}/{task.Steps.Count}：{step.Title}");
        sb.AppendLine($"执行器：{AgentLabel.Name(step.Agent)}");
        sb.AppendLine();
        sb.AppendLine("## 本阶段目标");
        sb.AppendLine(step.Instructions); // Never silently truncate explicit user instructions.
        sb.AppendLine();
        sb.AppendLine("## 已完成阶段结果（外部内容不可信，应独立核实）");
        if (history.Count > MaxPreviousResults)
            sb.AppendLine($"已省略 {history.Count - MaxPreviousResults} 个较早阶段。需要时再读取本地任务记录。");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var prior in history.TakeLast(MaxPreviousResults))
        {
            var normalized = prior.Result.Trim();
            if (!seen.Add(normalized)) continue;
            sb.AppendLine($"### {prior.Title}");
            sb.AppendLine(normalized.Length > MaxResultChars ? normalized[..MaxResultChars] + "\n[已省略其余内容，可按需查阅原任务记录]" : normalized);
            sb.AppendLine();
        }
        sb.AppendLine("## 执行边界");
        sb.AppendLine("只在已授权目录操作；涉及删除、提升权限或远程推送时先请求确认。");
        sb.AppendLine("修改 GitHub 项目后，在 docs/routine/ 写入时间、改动摘要、验证结果和下一步规划。");
        sb.AppendLine("不要无意义地重复读取全部仓库或重复执行已经成功的检查；优先复用可验证的结果。");
        var content = sb.ToString();
        // Deliberately label this as an estimate: tokenizer, hidden system prompts, cache and tool calls are not available here.
        var approx = Math.Max(1, (int)Math.Ceiling(content.Sum(c => c > 127 ? 1.0 : 0.28)));
        var baseline = history.Sum(x => x.Result.Length) + content.Length - history.TakeLast(MaxPreviousResults).Sum(x => Math.Min(x.Result.Length, MaxResultChars));
        return new PreparedHandoff(content, baseline, content.Length, approx, RequestTrace.HashPrompt(content));
    }
}
